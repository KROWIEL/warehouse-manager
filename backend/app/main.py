from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import init_db
from .routers import auth, catalog, products, profile, sales, stats, system
from .seed import run_seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    run_seed()
    yield


app = FastAPI(title="Store Manager", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(catalog.router)
app.include_router(products.router)
app.include_router(sales.router)
app.include_router(stats.router)
app.include_router(system.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ==== Раздача собранного фронтенда (SPA) ====
_assets_dir = settings.static_dir / "assets"
if _assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path.startswith("api/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    # Отдаём реальный файл, если он есть: favicon, манифест, service worker, wasm.
    if full_path:
        static_root = settings.static_dir.resolve()
        candidate = (static_root / full_path).resolve()
        if candidate.is_file() and candidate.is_relative_to(static_root):
            return FileResponse(candidate)

    index = settings.static_dir / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"detail": "Frontend не собран"}, status_code=404)
