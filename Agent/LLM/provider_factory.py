"""LLM provider factory — builds OpenAI or DeepSeek provider from config + env."""

import os

from Agent.Config.config import load_config


def build_provider(mode: str):
    cfg = load_config()
    if mode == "deepseek":
        key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not key:
            raise ValueError("Clé DEEPSEEK_API_KEY absente de la configuration.")
        from Agent.LLM.deepseek_provider import DeepSeekProvider
        return DeepSeekProvider(
            api_key=key,
            model=cfg["llm"]["deepseek_model"],
            base_url=cfg["llm"]["deepseek_base_url"],
            router_model=cfg["llm"]["deepseek_router_model"],
            simple_model=cfg["llm"]["deepseek_simple_model"],
            complex_model=cfg["llm"]["deepseek_complex_model"],
        )
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("Clé OPENAI_API_KEY absente de la configuration.")
    from Agent.LLM.openai_provider import OpenAIProvider
    return OpenAIProvider(
        api_key=key,
        model=cfg["llm"]["openai_model"],
        router_model=cfg["llm"]["openai_router_model"],
        simple_model=cfg["llm"]["openai_simple_model"],
        complex_model=cfg["llm"]["openai_complex_model"],
    )
