"""LLM-as-Reranker — re-rank retrieved chunks by relevance."""

import json
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

_BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(_BASE_DIR / "Agent" / ".env")


@lru_cache(maxsize=2)
def _get_client(mode: str = "openai"):
    from openai import OpenAI
    import os
    if mode == "deepseek":
        return OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com/v1")
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _model_name(mode: str) -> str:
    return "deepseek-chat" if mode == "deepseek" else "gpt-4o-mini"


def rerank_chunks(question: str, chunks: list[dict], top_n: int = 3,
                  mode: str = "openai") -> list[dict]:
    """Re-rank chunks by LLM relevance judgment.

    Retourne les top_n chunks re-classés par pertinence.
    Fallback : ordre vectoriel si JSON invalide.
    """
    if not chunks:
        return []

    client = _get_client(mode)
    model = _model_name(mode)

    docs = ""
    for i, c in enumerate(chunks):
        source = c.get("categorie", "")
        contenu = " ".join(filter(None, [
            c.get("titre", ""),
            c.get("objectif", ""),
            c.get("resume", ""),
        ]))[:500]
        docs += f"\n--- DOC {i} [{source}] ---\n{contenu}\n"

    try:
        r = client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=100,
            response_format={"type": "json_object"},
            messages=[
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
            ],
        )
        raw = r.choices[0].message.content
        ordre = json.loads(raw)["ranking"]
    except Exception:
        return chunks[:top_n]

    out = [chunks[i] for i in ordre if 0 <= i < len(chunks)]
    for c in chunks:
        if c not in out:
            out.append(c)
    return out[:top_n]
