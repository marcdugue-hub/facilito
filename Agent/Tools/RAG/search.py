from functools import lru_cache

from Agent.Config.config import load_config, get_project_root


@lru_cache(maxsize=1)
def _get_openai_collection():
    import chromadb
    cfg = load_config()
    client = chromadb.PersistentClient(path=str(get_project_root() / cfg["chroma"]["path"]))
    return client.get_collection(cfg["chroma"]["collection"])


@lru_cache(maxsize=1)
def _get_local_collection():
    import chromadb
    cfg = load_config()
    client = chromadb.PersistentClient(path=str(get_project_root() / cfg["chroma_local"]["path"]))
    return client.get_collection(cfg["chroma_local"]["collection"])


def search_practices(query: str, n_results: int = 5, embedding_mode: str = "local",
                     rewrite: bool = False, hyde: bool = False,
                     rerank: bool = False, rerank_mode: str = "openai",
                     provider=None) -> list[dict]:
    """Semantic search in ChromaDB. Returns list of practice metadata dicts.

    embedding_mode: "openai" → OpenAI ChromaDB, "local" → sentence-transformers ChromaDB.
    rewrite: if True, reformulate query via LLM before embedding search.
    hyde: if True, generate a hypothetical document via LLM and embed
          that instead of the query (HyDE method). Takes precedence over rewrite.
    rerank: if True, retrieve top-10 vectorially then re-rank with LLM (LLM-as-Reranker).
    rerank_mode: "openai" or "deepseek" — which LLM to use for re-ranking.
    provider: optional LLMProvider instance (avoids rebuilding).
    """
    if hyde:
        from Agent.Tools.RAG.hyde import generer_hypothese
        query = generer_hypothese(query, mode=rerank_mode, provider=provider)
    elif rewrite:
        from Agent.Tools.RAG.rewrite import rewrite_query
        query = rewrite_query(query, mode=rerank_mode, provider=provider)

    # When reranking, fetch enough candidates (at least 10) for the LLM to re-rank
    fetch_k = max(n_results, 10) if rerank else n_results

    if embedding_mode == "openai":
        from Agent.Tools.RAG.embedder import get_openai_embeddings
        query_embedding = get_openai_embeddings([query])[0]
        collection = _get_openai_collection()
    else:
        from Agent.Tools.RAG.embedder import get_embeddings
        query_embedding = get_embeddings([query])[0]
        collection = _get_local_collection()

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(fetch_k, collection.count()),
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

    if rerank and len(practices) > 1:
        from Agent.Tools.RAG.rerank import rerank_chunks
        practices = rerank_chunks(query, practices, top_n=n_results, mode=rerank_mode, provider=provider)

    return practices
