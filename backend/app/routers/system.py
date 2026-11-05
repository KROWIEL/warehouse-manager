import secrets
import sqlite3
import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from ..db import get_conn
from ..security import get_current_user

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/backup")
def download_backup(user: dict = Depends(get_current_user)):
    """Копия базы через sqlite3.backup(), а не простое копирование файла: при
    включённом WAL часть данных лежит в -wal, и скопированный на горячую файл
    может оказаться неполным."""
    tmp = Path(tempfile.gettempdir()) / f"store-backup-{secrets.token_hex(6)}.db"
    with get_conn() as src:
        dst = sqlite3.connect(tmp)
        try:
            src.backup(dst)
        finally:
            dst.close()

    return FileResponse(
        tmp,
        filename=f"store-backup-{date.today().isoformat()}.db",
        media_type="application/octet-stream",
        background=BackgroundTask(lambda: tmp.unlink(missing_ok=True)),
    )
