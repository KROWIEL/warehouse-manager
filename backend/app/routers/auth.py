from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from ..config import settings
from ..db import get_conn
from ..schemas import LoginIn
from ..security import (
    MIN_PASSWORD_LENGTH,
    SESSION_COOKIE,
    create_session,
    destroy_session,
    get_session_user,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def public_user(row: dict) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "avatar": row["avatar"],
        "theme": row["theme"],
        "must_change_password": bool(row["must_change_password"]),
    }


@router.post("/login")
def login(body: LoginIn, response: Response):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (body.username.strip().lower(),)
        ).fetchone()
    if row is None or not verify_password(body.password, row["salt"], row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")

    token = create_session(row["id"])
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=60 * 60 * 24 * settings.session_days,
        path="/",
    )
    return public_user(dict(row))


@router.post("/logout")
def logout(response: Response, sm_session: str | None = Cookie(default=None)):
    if sm_session:
        destroy_session(sm_session)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(get_session_user)):
    return public_user(user)


@router.get("/password-policy")
def password_policy():
    """Тексты требований живут на сервере, рядом с реальной проверкой; интерфейс
    сопоставляет их со своими подсказками по id, а не по порядку в списке."""
    return {
        "min_length": MIN_PASSWORD_LENGTH,
        "rules": [
            {"id": "length", "text": f"не короче {MIN_PASSWORD_LENGTH} символов"},
            {"id": "upper", "text": "хотя бы одна заглавная буква"},
            {"id": "lower", "text": "хотя бы одна строчная буква"},
            {"id": "special", "text": "хотя бы один специальный символ, например ! ? * # @"},
        ],
    }
