"""LLM config REST routes."""

from fastapi import APIRouter, HTTPException, Request

from Agent.LLM.provider_factory import build_provider
from Agent.Tools.Memory.store import clear_all_history
from Agent.Main.models import LLMConfig

router = APIRouter(tags=["config"])


@router.get("/api/config/llm")
def get_llm_config(request: Request):
    return {"mode": request.app.state.llm_mode}


@router.post("/api/config/llm")
def set_llm_config(request: Request, body: LLMConfig):
    mode = body.mode
    if mode not in ("openai", "deepseek"):
        raise HTTPException(400, "Mode invalide. Choisir 'openai' ou 'deepseek'.")
    try:
        request.app.state.provider = build_provider(mode)
        request.app.state.llm_mode = mode
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    clear_all_history()
    return {"mode": mode}
