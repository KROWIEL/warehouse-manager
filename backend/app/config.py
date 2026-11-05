import os
from pathlib import Path

# Сколько переменных SEED_USER{N}_* просматривать. Пропуски в нумерации допустимы,
# поэтому не останавливаемся на первой отсутствующей, а сканируем весь диапазон.
MAX_SEED_USERS = 50


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Простые настройки из переменных окружения (без лишних зависимостей)."""

    def __init__(self) -> None:
        self.data_dir = Path(os.getenv("DATA_DIR", "/data"))
        self.db_path = self.data_dir / "store.db"

        self.session_days = int(os.getenv("SESSION_DAYS", "30"))
        # Secure-cookie: включать за HTTPS (прод на VDS). Для локального http — false.
        self.cookie_secure = _bool(os.getenv("COOKIE_SECURE"), False)

        # Статика собранного фронтенда
        self.static_dir = Path(os.getenv("STATIC_DIR", "/app/static"))

        # Сколько дней без продаж считать «мёртвым стоком»
        self.dead_stock_days = int(os.getenv("DEAD_STOCK_DAYS", "60"))

        self.seed_users = self._read_seed_users()

    def _read_seed_users(self) -> list[dict]:
        users: list[dict] = []
        seen: set[str] = set()
        for idx in range(1, MAX_SEED_USERS + 1):
            username = os.getenv(f"SEED_USER{idx}_USERNAME")
            if not username or not username.strip():
                continue
            password = os.getenv(f"SEED_USER{idx}_PASSWORD")
            # Опечатка в имени переменной иначе тихо съест аккаунт: пользователь
            # указал N аккаунтов, а создалось меньше и без объяснений.
            if not password:
                raise RuntimeError(
                    f"SEED_USER{idx}_USERNAME задан, а SEED_USER{idx}_PASSWORD — нет. "
                    "Проверьте .env"
                )
            login = username.strip().lower()
            if login in seen:
                raise RuntimeError(f"Логин «{login}» указан в .env несколько раз")
            seen.add(login)
            users.append(
                {
                    "username": login,
                    "display_name": os.getenv(f"SEED_USER{idx}_NAME", username).strip(),
                    "password": password,
                    "avatar": os.getenv(f"SEED_USER{idx}_AVATAR", "fox").strip(),
                }
            )
        return users


settings = Settings()
