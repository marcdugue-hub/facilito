from functools import lru_cache
from pathlib import Path

import yaml

_BASE_DIR = Path(__file__).resolve().parents[3]


def _load_config() -> dict:
    with open(_BASE_DIR / "Agent" / "Config" / "app_config.yaml") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def _get_collection():
    import chromadb
    cfg = _load_config()
    client = chromadb.PersistentClient(path=str(_BASE_DIR / cfg["chroma"]["path"]))
    return client.get_collection(cfg["chroma"]["collection"])


def search_practices(query: str, n_results: int = 5) -> list[dict]:
    """Semantic search in ChromaDB. Returns list of practice metadata dicts."""
    from Agent.Tools.RAG.embedder import get_embeddings

    query_embedding = get_embeddings([query])[0]

    collection = _get_collection()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, collection.count()),
        include=["metadatas", "documents", "distances"],
    )

    practices = []
    for i, meta in enumerate(results["metadatas"][0]):
        practices.append({
            "practice_id": results["ids"][0][i],
            "titre": meta.get("titre", ""),
            "categorie": meta.get("categorie", ""),
            "phase": meta.get("phase", ""),
            "difficulte": meta.get("difficulte", ""),
            "duree": meta.get("duree", ""),
            "duration_minutes": meta.get("duration_minutes", 30),
            "participants": meta.get("participants", ""),
            "icone_code": meta.get("icone_code", ""),
            "url": meta.get("url", ""),
            "objectif": meta.get("objectif", ""),
            "resume": meta.get("resume", ""),
            "score": round(1 - results["distances"][0][i], 3),
        })
    return practices
