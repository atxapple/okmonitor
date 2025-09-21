from __future__ import annotations

from fastapi import FastAPI

from .routes import router as ui_router


def register_ui(app: FastAPI) -> None:
    """Attach the UI router to the FastAPI application."""
    app.include_router(ui_router)


__all__ = ["register_ui"]
