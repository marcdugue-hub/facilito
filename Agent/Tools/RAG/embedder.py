"""Embedding functions — local (sentence-transformers) and OpenAI."""
from functools import lru_cache

from Agent.Config.config import load_config


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer
    cfg = load_config()
    return SentenceTransformer(cfg["embedding"]["model"])


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Local embedding via sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2)."""
    model = _get_model()
    emb = model.encode(texts, normalize_embeddings=True)
    return emb.tolist()


def get_openai_embeddings(texts: list[str]) -> list[list[float]]:
    """OpenAI embedding via text-embedding-3-small API."""
    import os
    from openai import OpenAI
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for OpenAI embeddings")
    client = OpenAI(api_key=api_key)
    cfg = load_config()
    model = cfg["embedding"]["openai_model"]
    response = client.embeddings.create(model=model, input=texts)
    return [d.embedding for d in response.data]
