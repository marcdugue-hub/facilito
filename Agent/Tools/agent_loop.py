"""Agent chat loop: orchestrates LLM calls, tool dispatch, and resolution."""

import json
import time
import os

from Agent.Tools.Database import sessions as db_ses
from Agent.Tools.Database.analytics import log_event, get_cost_config
from Agent.Prompts.system_prompt import build_system_prompt
from Agent.Tools.Memory.store import get_history, add_message
from Agent.Tools.security import (
    call_llm_with_retry,
    filter_sensitive_data,
    validate_request_rate,
    validate_user_input,
)
from Agent.Observability.langfuse_handler import (
    create_trace, create_llm_generation, flush as langfuse_flush,
)
from Agent.Tools.erreur import (
    ExternalServiceError,
    InvalidAPIKeyError,
    LLMTimeoutError,
    RateLimitError,
    InvalidUserInputError,
    InjectionDetectedError,
)
from Agent.Tools.tools_schema import TOOLS, SESSION_SCOPED
from Agent.Tools.tool_dispatch import dispatch_tool, _is_rag_fallback
from Agent.Config.config import load_config


def run_agent_chat(
    provider,
    session_id: int,
    user_msg: str,
    llm_mode: str,
) -> dict:
    start_time = time.time()

    try:
        validate_request_rate(session_id)
        user_msg = validate_user_input(user_msg)
    except InvalidUserInputError as exc:
        raise  # propagated to route handler
    except InjectionDetectedError as exc:
        raise
    except RateLimitError as exc:
        raise

    cfg = load_config()
    from Agent.Tools.intent_classifier import classifier_intent
    routing = classifier_intent(provider, user_msg, session_id, cfg)
    complexity = routing["complexite"]
    categorie = routing["categorie"]

    if complexity == "complexe":
        current_model = provider._complex_model
        reasoning_effort = None
    else:
        current_model = provider._simple_model
        reasoning_effort = None

    cost_cfg = get_cost_config()
    trace = create_trace(
        "agent_chat",
        session_id=str(session_id) if session_id else None,
        metadata={
            "llm_mode": llm_mode,
            "session_id": session_id,
            "complexite": complexity,
            "categorie": categorie,
            "model_used": current_model,
        },
        input=user_msg,
    )

    ctx = db_ses.get_session_context(session_id)
    system_prompt = build_system_prompt(ctx)
    history = get_history(session_id)

    messages = [{"role": "system", "content": system_prompt}] + history + [
        {"role": "user", "content": user_msg}
    ]

    tool_results = []
    max_iterations = 10
    for iteration in range(max_iterations):
        llm_start = time.time()

        request_messages = []
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            tc = m.get("tool_calls")
            if role == "system":
                request_messages.append({"role": "system", "content": content[:600] + ("…" if len(content) > 600 else "")})
            elif tc:
                names = [t["function"]["name"] for t in tc]
                request_messages.append({"role": "assistant", "tool_calls": names})
            else:
                request_messages.append({"role": role, "content": content[:800]})

        log_event(
            session_id=session_id,
            event_type="llm",
            summary=f"LLM → appel #{iteration+1} en cours… ({current_model})",
            payload=json.dumps({
                "mode": llm_mode,
                "complexite": complexity,
                "categorie": categorie,
                "model": current_model,
                "status": "pending",
                "request": request_messages,
            }, ensure_ascii=False),
            tokens_in=0,
            tokens_out=0,
            duration_ms=0,
        )

        try:
            response, usage = call_llm_with_retry(
                provider,
                messages,
                TOOLS,
                timeout=int(os.environ.get("LLM_TIMEOUT_SECONDS", 20)),
                max_retries=3,
                model=current_model,
                reasoning_effort=reasoning_effort,
            )
        except LLMTimeoutError as exc:
            log_event(
                session_id=session_id,
                event_type="llm",
                summary="LLM timeout",
                payload=str(exc),
                duration_ms=int((time.time() - llm_start) * 1000),
            )
            langfuse_flush()
            raise
        except InvalidAPIKeyError:
            langfuse_flush()
            raise
        except ExternalServiceError as exc:
            langfuse_flush()
            raise

        llm_ms = int((time.time() - llm_start) * 1000)

        t_in = usage.get("prompt_tokens", 0)
        t_out = usage.get("completion_tokens", 0)

        cost = (t_in * cost_cfg["cost_in"] + t_out * cost_cfg["cost_out"]) / 1_000_000
        create_llm_generation(
            trace, "llm_call",
            model=current_model,
            messages=messages, response=response, usage=usage,
            duration_ms=llm_ms, cost=cost,
        )

        payload = json.dumps({
            "mode": llm_mode,
            "complexite": complexity,
            "categorie": categorie,
            "model": current_model,
            "status": "done",
            "request": request_messages,
            "tool_calls_requested": len(response.get("tool_calls") or []),
            "response_preview": (response.get("content") or "")[:600],
        }, ensure_ascii=False)
        log_event(
            session_id=session_id,
            event_type="llm",
            summary=f"LLM ({current_model}) — {t_in}T in, {t_out}T out — {llm_ms}ms",
            payload=payload,
            tokens_in=t_in,
            tokens_out=t_out,
            duration_ms=llm_ms,
        )

        tool_calls = response.get("tool_calls") or []
        if not tool_calls:
            raw_text = response.get("content") or ""
            if "||NON_RÉSOLU||" in raw_text:
                resolved = False
                display_text = raw_text.replace("||NON_RÉSOLU||", "").strip()
            else:
                resolved = True
                display_text = raw_text.replace("||RÉSOLU||", "").strip()

            display_text = filter_sensitive_data(display_text)

            total_ms = int((time.time() - start_time) * 1000)
            log_event(
                session_id=session_id,
                event_type="resolution",
                summary=f"{'✓ Résolu' if resolved else '✗ Non résolu'} — {total_ms}ms ({current_model})",
                payload=json.dumps({"resolved": resolved, "reply_preview": display_text[:200], "model": current_model, "categorie": categorie}),
                duration_ms=total_ms,
                resolved=resolved,
            )

            add_message(session_id, "user", user_msg)
            add_message(session_id, "assistant", display_text)
            langfuse_flush()
            return {"reply": display_text, "tool_results": tool_results, "complexite": complexity, "categorie": categorie}

        messages.append(response)

        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = json.loads(tc["function"]["arguments"])

            if fn_name in SESSION_SCOPED and session_id:
                fn_args["session_id"] = session_id

            tool_start = time.time()
            try:
                em = "openai" if llm_mode == "openai" else "local"
                result_str = dispatch_tool(fn_name, fn_args, session_id=session_id, embedding_mode=em, llm_mode=llm_mode)
            except Exception as exc:
                result_str = json.dumps({"error": str(exc)})

            tool_ms = int((time.time() - tool_start) * 1000)

            is_rag = fn_name == "search_practices"
            fallback = _is_rag_fallback(fn_name, result_str)
            log_event(
                session_id=session_id,
                event_type="rag" if is_rag else "db",
                summary=f"{fn_name}({', '.join(f'{k}={v}' for k, v in fn_args.items())[:80]}) — {tool_ms}ms",
                payload=result_str[:2000],
                duration_ms=tool_ms,
                fallback=fallback,
            )

            parsed_result = json.loads(result_str)
            safe_result = filter_sensitive_data(parsed_result)
            if fn_name == "create_session" and isinstance(parsed_result, dict) and parsed_result.get("id"):
                session_id = parsed_result["id"]

            tool_results.append({"tool": fn_name, "args": fn_args, "result": safe_result})
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result_str})

    total_ms = int((time.time() - start_time) * 1000)
    log_event(session_id=session_id, event_type="resolution",
              summary=f"✗ Max itérations — {total_ms}ms",
              payload="{}", duration_ms=total_ms, resolved=False)
    langfuse_flush()
    return {"reply": "Désolé, la requête a pris trop de cycles.", "tool_results": tool_results, "complexite": complexity, "categorie": categorie}
