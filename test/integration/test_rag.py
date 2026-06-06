"""Tests d'intégration — Agent/Tools/RAG/ (ChromaDB réel).

Vérifie que la base vectorielle ChromaDB locale est accessible et
que les recherches sémantiques retournent des résultats cohérents.
Ignorés si la collection locale n'existe pas (init_rag --local)."""
import pytest


@pytest.fixture(autouse=True)
def clear_rag_cache():
    from Agent.Tools.RAG.search import _get_local_collection, _get_openai_collection
    _get_local_collection.cache_clear()
    _get_openai_collection.cache_clear()
    yield
    _get_local_collection.cache_clear()
    _get_openai_collection.cache_clear()


@pytest.mark.rag_local
class TestRAGLocal:
    def test_collection_exists_and_has_data(self):
        from Agent.Tools.RAG.search import _get_local_collection
        coll = _get_local_collection()
        count = coll.count()
        assert count > 0, f"Collection locale vide ({count} documents). Lancez init_rag --local"

    def test_search_returns_results(self):
        from Agent.Tools.RAG.search import search_practices
        results = search_practices("brainstorming", embedding_mode="local")
        assert len(results) > 0
        assert results[0]["titre"]
        assert results[0]["score"] > 0

    def test_search_result_structure(self):
        from Agent.Tools.RAG.search import search_practices
        results = search_practices("icebreaker", embedding_mode="local")
        assert len(results) > 0
        required = {"practice_id", "titre", "categorie", "phase", "score",
                    "duration_minutes", "duree", "objectif", "resume"}
        assert required.issubset(results[0].keys())

    def test_search_different_queries_return_different_results(self):
        from Agent.Tools.RAG.search import search_practices
        r1 = search_practices("brainstorming créatif", embedding_mode="local")
        r2 = search_practices("évaluation rétrospective", embedding_mode="local")
        ids_1 = {p["practice_id"] for p in r1[:3]}
        ids_2 = {p["practice_id"] for p in r2[:3]}
        assert ids_1 != ids_2, "Deux requêtes différentes devraient retourner des résultats différents"

    def test_search_empty_query_returns_results(self):
        from Agent.Tools.RAG.search import search_practices
        results = search_practices("", embedding_mode="local")
        assert len(results) > 0

    def test_n_results_is_respected(self):
        from Agent.Tools.RAG.search import search_practices
        results = search_practices("atelier", n_results=3, embedding_mode="local")
        assert len(results) <= 3

    def test_scores_are_within_range(self):
        from Agent.Tools.RAG.search import search_practices
        results = search_practices("collaboration", embedding_mode="local")
        for p in results:
            assert 0 <= p["score"] <= 1


@pytest.mark.openai
class TestRAGOpenAI:
    def test_openai_collection_exists(self):
        from Agent.Tools.RAG.search import _get_openai_collection
        try:
            coll = _get_openai_collection()
            count = coll.count()
        except Exception:
            pytest.skip("Collection ChromaDB OpenAI introuvable. Lancez : python -m Agent.Tools.RAG.init_rag")
        assert count > 0

    def test_openai_search_returns_results(self):
        from Agent.Tools.RAG.search import search_practices
        try:
            results = search_practices("animation d'équipe", embedding_mode="openai")
        except Exception:
            pytest.skip("Collection ChromaDB OpenAI introuvable. Lancez : python -m Agent.Tools.RAG.init_rag")
        assert len(results) > 0
        assert results[0]["score"] > 0
