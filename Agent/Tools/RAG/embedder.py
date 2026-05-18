"""Local embedding via sentence-transformers. Lazy model loading."""
from functools import lru_cache
from pathlib import Path

import yaml

_BASE_DIR = Path(__file__).resolve().parents[3]


def _load_config() -> dict:
    with open(_BASE_DIR / "Agent" / "Config" / "app_config.yaml") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer
    cfg = _load_config()
    return SentenceTransformer(cfg["embedding"]["model"])


def get_embeddings(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    emb = model.encode(texts, normalize_embeddings=True)
    return emb.tolist()
