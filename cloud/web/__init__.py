from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes import router as ui_router


def register_ui(app: FastAPI) -> None:
    """Attach the UI router to the FastAPI application."""
    # Mount static files directory for favicon and logo
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/ui/static", StaticFiles(directory=str(static_dir)), name="ui_static")

    app.include_router(ui_router)


__all__ = ["register_ui"]
