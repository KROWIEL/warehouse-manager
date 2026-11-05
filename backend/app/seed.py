from .config import settings
from .constants import VALID_AVATARS
from .db import get_conn
from .security import hash_password, make_salt


def run_seed() -> None:
    """Создаёт аккаунты, перечисленные в .env. Проверка идёт по каждому логину
    отдельно, а не по «база пустая» — так позже можно дописать в .env ещё один
    аккаунт, и он появится, не задев уже существующие и их пароли."""
    if not settings.seed_users:
        return

    with get_conn() as conn:
        existing = {row["username"] for row in conn.execute("SELECT username FROM users")}
        new_users = [u for u in settings.seed_users if u["username"] not in existing]
        if not new_users:
            return
        for u in new_users:
            salt = make_salt()
            avatar = u["avatar"] if u["avatar"] in VALID_AVATARS else "fox"
            conn.execute(
                """
                INSERT INTO users (username, display_name, password_hash, salt, avatar)
                VALUES (?, ?, ?, ?, ?)
                """,
                (u["username"], u["display_name"], hash_password(u["password"], salt), salt, avatar),
            )
        conn.commit()
