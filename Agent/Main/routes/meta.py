"""Meta REST routes (index + mascots)."""

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pathlib import Path

from Agent.Config.config import get_project_root

router = APIRouter(tags=["meta"])

_static_dir = Path(__file__).resolve().parent.parent / "static"


@router.get("/")
def index():
    return FileResponse(str(_static_dir / "index.html"))


@router.get("/api/mascots")
def get_mascots():
    mascotte_dir = get_project_root() / "Mascotte"
    files = [f.name for f in mascotte_dir.iterdir() if f.suffix.lower() in {".png", ".jpg", ".jpeg"}]
    return sorted(files)
