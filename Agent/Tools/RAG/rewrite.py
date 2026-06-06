"""Query rewriting for RAG — reformulates questions to optimize practice search."""

from Agent.Tools.security import call_llm_with_retry
from Agent.LLM.provider_factory import build_provider


def rewrite_query(question: str, mode: str = "openai", provider=None) -> str:
    """Reformulate a natural-language question for optimal RAG retrieval.

    Uses gpt-4o-mini (temperature 0) to produce a focused, technical query
    suited to the facilitation-practice domain.
    """
    if provider is None:
        provider = build_provider(mode)
    model = provider._simple_model

    messages = [
        {
            "role": "system",
            "content": (
                "Reformule la question pour optimiser une recherche "
                "de pratiques de facilitation d'ateliers collaboratifs. "
                "Utilise des termes techniques précis (type de pratique, "
                "phase d'atelier, objectif, nombre de participants, durée, "
                "catégorie). Réponds UNIQUEMENT la question reformulée, "
                "sans préfixe ni ponctuation superflue."
            ),
        },
        {"role": "user", "content": question},
    ]

    response, usage = call_llm_with_retry(
        provider, messages, max_retries=2, timeout=15, model=model,
    )
    return response.get("content", "").strip()
