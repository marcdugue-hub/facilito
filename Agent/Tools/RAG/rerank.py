"""LLM-as-Reranker — re-rank retrieved chunks by relevance."""

import json

from Agent.Tools.security import call_llm_with_retry
from Agent.LLM.provider_factory import build_provider


def rerank_chunks(question: str, chunks: list[dict], top_n: int = 3,
                  mode: str = "openai", provider=None) -> list[dict]:
    """Re-rank chunks by LLM relevance judgment.

    Retourne les top_n chunks re-classés par pertinence.
    Fallback : ordre vectoriel si JSON invalide.
    """
    if not chunks:
        return []

    if provider is None:
        provider = build_provider(mode)
    model = provider._simple_model

    docs = ""
    for i, c in enumerate(chunks):
        source = c.get("categorie", "")
        contenu = " ".join(filter(None, [
            c.get("titre", ""),
            c.get("objectif", ""),
            c.get("resume", ""),
        ]))[:500]
        docs += f"\n--- DOC {i} [{source}] ---\n{contenu}\n"

    messages = [
        {
            "role": "system",
            "content": (
                f"Classe TOUS les {len(chunks)} documents du PLUS au MOINS pertinent "
                f"par rapport à la question. "
                'Réponds UNIQUEMENT au format JSON {"ranking":[indices]} avec TOUS '
                f"les indices de 0 à {len(chunks)-1}."
            ),
        },
        {
            "role": "user",
            "content": f"QUESTION : {question}\n\nDOCUMENTS :{docs}",
        },
    ]

    try:
        response, usage = call_llm_with_retry(
            provider, messages, max_retries=2, timeout=15, model=model,
        )
        raw = response.get("content", "")
        ordre = json.loads(raw)["ranking"]
    except Exception:
        return chunks[:top_n]

    out = [chunks[i] for i in ordre if 0 <= i < len(chunks)]
    for c in chunks:
        if c not in out:
            out.append(c)
    return out[:top_n]
