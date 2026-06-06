"""App settings REST routes (feature toggles)."""

from fastapi import APIRouter, HTTPException

from Agent.Tools.Database.analytics import get_app_setting, set_app_setting
from Agent.Main.models import ToggleBody

router = APIRouter(tags=["settings"])

_ALLOWED_SETTINGS = {"voice", "query_rewriting", "hyde", "rerank"}
_SETTING_DB_KEYS = {"voice": "voice_mode"}


@router.get("/api/settings/{setting}")
def get_setting(setting: str):
    if setting not in _ALLOWED_SETTINGS:
        raise HTTPException(404, f"Unknown setting: {setting}")
    db_key = _SETTING_DB_KEYS.get(setting, setting)
    return {"enabled": get_app_setting(db_key) == "on"}


@router.post("/api/settings/{setting}")
def set_setting(setting: str, body: ToggleBody):
    if setting not in _ALLOWED_SETTINGS:
        raise HTTPException(404, f"Unknown setting: {setting}")
    db_key = _SETTING_DB_KEYS.get(setting, setting)
    set_app_setting(db_key, "on" if body.enabled else "off")
    return {"enabled": body.enabled}
