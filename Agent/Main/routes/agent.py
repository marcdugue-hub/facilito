"""Agent chat REST route."""

from fastapi import APIRouter, HTTPException, Request

from Agent.Tools.erreur import (
    ExternalServiceError,
    InvalidAPIKeyError,
    InvalidUserInputError,
    InjectionDetectedError,
    LLMTimeoutError,
    RateLimitError,
)
from Agent.Tools.agent_loop import run_agent_chat
from Agent.Main.models import ChatMessage

router = APIRouter(tags=["agent"])


@router.post("/api/agent/chat")
def agent_chat(request: Request, body: ChatMessage):
    try:
        return run_agent_chat(
            provider=request.app.state.provider,
            session_id=body.session_id,
            user_msg=body.message,
            llm_mode=request.app.state.llm_mode,
        )
    except InvalidUserInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except InjectionDetectedError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except LLMTimeoutError:
        raise HTTPException(status_code=504, detail="Le service LLM n'a pas répondu à temps.")
    except InvalidAPIKeyError:
        raise HTTPException(status_code=401, detail="Clé API invalide.")
    except ExternalServiceError as exc:
        raise HTTPException(status_code=502, detail=f"Erreur externe du LLM : {str(exc)}")
