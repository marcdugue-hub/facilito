"""Query rewriting for RAG — reformulates questions to optimize practice search."""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

_BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(_BASE_DIR / "Agent" / ".env")


@lru_cache(maxsize=1)
def _get_client():
    from openai import OpenAI
    import os
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def rewrite_query(question: str) -> str:
    """Reformulate a natural-language question for optimal RAG retrieval.

    Uses gpt-4o-mini (temperature 0) to produce a focused, technical query
    suited to the facilitation-practice domain.
    """
    client = _get_client()
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        max_tokens=100,
        messages=[
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
        ],
    )
    return r.choices[0].message.content.strip()
