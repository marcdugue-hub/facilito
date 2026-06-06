"""LangFuse observability — traces, generations, cost tracking."""

import os
import time
from typing import Optional

from langfuse import Langfuse

_langfuse: Optional[Langfuse] = None


def get_langfuse() -> Optional[Langfuse]:
    global _langfuse
    if _langfuse is None:
        pk = os.environ.get("LANGFUSE_PUBLIC_KEY")
        sk = os.environ.get("LANGFUSE_SECRET_KEY")
        if not pk or not sk:
            return None
        host = os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
        _langfuse = Langfuse(public_key=pk, secret_key=sk, host=host)
    return _langfuse


def is_enabled() -> bool:
    return get_langfuse() is not None


def create_trace(name: str, **kwargs):
    lf = get_langfuse()
    if lf is None:
        return None
    return lf.trace(name=name, **kwargs)


def create_llm_generation(
    trace,
    name: str,
    model: str,
    messages: list,
    response: dict,
    usage: dict,
    duration_ms: int,
    cost: Optional[float] = None,
):
    if trace is None:
        return
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    generation = trace.generation(
        name=name,
        model=model,
        input=messages,
        output=response,
        usage={
            "input": prompt_tokens,
            "output": completion_tokens,
            "unit": "TOKENS",
        },
        start_time=time.time() - duration_ms / 1000,
        end_time=time.time(),
    )
    if cost is not None:
        generation.score(name="cost", value=cost)


def flush():
    lf = get_langfuse()
    if lf is not None:
        lf.flush()
