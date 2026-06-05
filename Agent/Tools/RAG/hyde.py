"""HyDE (Hypothetical Document Embeddings) for RAG — generates a hypothetical document
to use as the search query instead of the raw question."""

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


def generer_hypothese(question: str) -> str:
    """Generate a hypothetical document answering the question.

    The hypothesis is written as an excerpt from an official CNIL/RGPD guide.
    It is NEVER shown to the user — only used as a search query for RAG.
    """
    client = _get_client()
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.3,
        max_tokens=180,
        messages=[
            {
                "role": "system",
                "content": (
                    "Redige un court paragraphe repondant a la question, "
                    "comme un extrait de guide CNIL/RGPD officiel."
                ),
            },
            {"role": "user", "content": question},
        ],
    )
    return r.choices[0].message.content.strip()
