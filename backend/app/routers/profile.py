from fastapi import APIRouter, Depends, HTTPException, status

from ..constants import VALID_AVATARS, VALID_THEMES
from ..db import get_conn
from ..schemas import PasswordIn, ProfileIn
from ..security import (
    get_current_user,
    get_session_user,
    hash_password,
    make_salt,
    password_problem,
    verify_password,
)
from .auth import public_user

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("/users")
def list_users(user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, display_name, avatar FROM users ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


@router.patch("")
def update_profile(body: ProfileIn, user: dict = Depends(get_current_user)):
    fields, values = [], []
    if body.display_name is not None:
        fields.append("display_name = ?")
        values.append(body.display_name.strip())
    if body.avatar is not None:
        if body.avatar not in VALID_AVATARS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неизвестный аватар")
        fields.append("avatar = ?")
        values.append(body.avatar)
    if body.theme is not None:
        if body.theme not in VALID_THEMES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неизвестная тема")
        fields.append("theme = ?")
        values.append(body.theme)

    with get_conn() as conn:
        if fields:
            conn.execute(
                f"UPDATE users SET {', '.join(fields)} WHERE id = ?", [*values, user["id"]]
            )
            conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    return public_user(dict(row))


@router.post("/password")
def change_password(body: PasswordIn, user: dict = Depends(get_session_user)):
    """Доступно и до снятия флага must_change_password — это единственный способ
    его снять."""
    if not verify_password(body.current_password, user["salt"], user["password_hash"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Текущий пароль неверный")
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Новый пароль совпадает с текущим")
    problem = password_problem(body.new_password)
    if problem:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)

    salt = make_salt()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE users
            SET password_hash = ?, salt = ?, must_change_password = 0
            WHERE id = ?
            """,
            (hash_password(body.new_password, salt), salt, user["id"]),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    return public_user(dict(row))
