"""FastAPI app: 4 API gon /ask /upload/legal /upload/draft /audit."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.doisanh.api.routes_simple import router as simple_router
from app.core.config import settings

logging.basicConfig(level=settings.LOG_LEVEL, format="%(levelname)s %(name)s %(message)s")

app = FastAPI(title="audit-legal", version="0.4.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
app.include_router(simple_router)

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# Cac path la trang SPA -> deu tra ve index.html (routing phia client doc location.pathname)
@app.get("/", response_class=HTMLResponse)
@app.get("/audit", response_class=HTMLResponse)
@app.get("/legal", response_class=HTMLResponse)
def home() -> str:
    index = STATIC_DIR / "index.html"
    if index.exists():
        return index.read_text(encoding="utf-8")
    return "<h1>audit-legal</h1><p>UI chua co, dung /docs cho API</p>"


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
