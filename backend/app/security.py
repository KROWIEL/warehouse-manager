import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import Cookie, Depends, HTTPException, status

from .config import settings
from .db import get_conn

SESSION_COOKIE = "sm_session"

# PBKDF2-SHA256 из стандартной библиотеки: столько же кода, сколько наивный хеш,
# но пароль реально нельзя восстановить по базе. Требование «строгий пароль»
# вместе со слабым хешем не имело бы смысла.
_PBKDF2_ROUNDS = 200_000

MIN_PASSWORD_LENGTH = 8


def make_salt() -> str:
    return secrets.token_hex(16)


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ROUNDS
    ).hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password, salt), expected_hash)


def password_problem(password: str) -> str | None:
    """Возвращает описание проблемы или None, если пароль подходит.
    Единственный источник правды о политике — фронтенд только дублирует подсказки."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов"
    if not any(c.isupper() for c in password):
        return "В пароле нужна хотя бы одна заглавная буква"
    if not any(c.islower() for c in password):
        return "В пароле нужна хотя бы одна строчная буква"
    if not any(not c.isalnum() and not c.isspace() for c in password):
        return "В пароле нужен хотя бы один специальный символ, например ! ? * # @"
    return None


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.utcnow() + timedelta(days=settings.session_days)).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires),
        )
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (datetime.utcnow().isoformat(),))
        conn.commit()
    return token


def destroy_session(token: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()


def get_session_user(sm_session: str | None = Cookie(default=None)) -> dict:
    """Только проверка сессии. Нужна там, где пользователь ещё обязан сменить
    пароль: /auth/me, /auth/logout и сама смена пароля."""
    if not sm_session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Не авторизован")
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT u.* FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND s.expires_at > ?
            """,
            (sm_session, datetime.utcnow().isoformat()),
        ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия истекла")
    return dict(row)


def get_current_user(user: dict = Depends(get_session_user)) -> dict:
    """Рабочая авторизация: до смены стартового пароля доступа к данным нет.
    Проверка на сервере, а не только в интерфейсе."""
    if user["must_change_password"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Сначала нужно сменить пароль")
    return user
