"""HyDE (Hypothetical Document Embeddings) for RAG — generates a hypothetical document
to use as the search query instead of the raw question."""

from Agent.Tools.security import call_llm_with_retry
from Agent.LLM.provider_factory import build_provider


def generer_hypothese(question: str, mode: str = "openai", provider=None) -> str:
    """Generate a hypothetical document answering the question.

    The hypothesis is written as an excerpt from a facilitation practice guide.
    It is NEVER shown to the user — only used as a search query for RAG.
    """
    if provider is None:
        provider = build_provider(mode)
    model = provider._simple_model

    messages = [
        {
            "role": "system",
            "content": (
                "Redige un court paragraphe repondant a la question, "
                "comme un extrait de fiche pratique d'atelier collaboratif. "
                "Decris les objectifs, le deroule, les consignes et le materiel necessaire."
            ),
        },
        {"role": "user", "content": question},
    ]

    response, usage = call_llm_with_retry(
        provider, messages, max_retries=2, timeout=15, model=model,
    )
    return response.get("content", "").strip()
