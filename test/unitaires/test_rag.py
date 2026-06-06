"""Tests unitaires — Agent/Tools/RAG/search.py + _is_rag_fallback dans tool_dispatch.py"""
import json
from unittest.mock import patch, MagicMock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_embedding():
    return [[0.1] * 384]


def _fake_collection(meta_list, distance_list, id_list):
    coll = MagicMock()
    coll.count.return_value = len(meta_list)
    coll.query.return_value = {
        "ids": [id_list],
        "metadatas": [meta_list],
        "documents": [[""] * len(meta_list)],
        "distances": [distance_list],
    }
    return coll


_SAMPLE_META = {
    "titre": "Brainstorming",
    "categorie": "Générer des idées",
    "phase": "Exploration",
    "difficulte": "Facile",
    "duree": "45'",
    "duration_minutes": 45,
    "participants": "5-20",
    "icone_code": "ID02",
    "url": "https://example.com",
    "objectif": "Générer des idées librement",
    "resume": "Technique de créativité collective",
}


# ── search_practices ──────────────────────────────────────────────────────────

def test_search_practices_returns_results():
    from Agent.Tools.RAG.search import search_practices, _get_local_collection
    _get_local_collection.cache_clear()

    with patch("Agent.Tools.RAG.search._get_local_collection",
               return_value=_fake_collection([_SAMPLE_META], [0.1], ["1"])), \
         patch("Agent.Tools.RAG.embedder.get_embeddings",
               return_value=_fake_embedding()):

        results = search_practices("idées créatives", n_results=3)

    assert len(results) == 1
    assert results[0]["titre"] == "Brainstorming"
    assert results[0]["score"] == pytest_approx(0.9, abs=0.001)


def test_search_practices_score_computed_as_one_minus_distance():
    from Agent.Tools.RAG.search import search_practices, _get_local_collection
    _get_local_collection.cache_clear()

    with patch("Agent.Tools.RAG.search._get_local_collection",
               return_value=_fake_collection([_SAMPLE_META], [0.25], ["1"])), \
         patch("Agent.Tools.RAG.embedder.get_embeddings",
               return_value=_fake_embedding()):

        results = search_practices("test")

    assert abs(results[0]["score"] - 0.75) < 0.001


def test_search_practices_empty_collection_returns_empty_list():
    from Agent.Tools.RAG.search import search_practices, _get_local_collection
    _get_local_collection.cache_clear()

    with patch("Agent.Tools.RAG.search._get_local_collection",
               return_value=_fake_collection([], [], [])), \
         patch("Agent.Tools.RAG.embedder.get_embeddings",
               return_value=_fake_embedding()):

        results = search_practices("icebreaker", n_results=5)

    assert results == []


def test_search_practices_n_results_capped_by_collection_size():
    from Agent.Tools.RAG.search import search_practices, _get_local_collection
    _get_local_collection.cache_clear()

    meta_list = [_SAMPLE_META, {**_SAMPLE_META, "titre": "Méthode B"}]
    with patch("Agent.Tools.RAG.search._get_local_collection",
               return_value=_fake_collection(meta_list, [0.1, 0.2], ["1", "2"])), \
         patch("Agent.Tools.RAG.embedder.get_embeddings",
               return_value=_fake_embedding()):

        results = search_practices("test", n_results=10)

    assert len(results) == 2


# ── _is_rag_fallback ──────────────────────────────────────────────────────────

def test_is_rag_fallback_low_score():
    from Agent.Tools.tool_dispatch import _is_rag_fallback
    result_str = json.dumps([{"practice_id": "1", "score": 0.15}])
    assert _is_rag_fallback("search_practices", result_str) is True


def test_is_rag_fallback_high_score():
    from Agent.Tools.tool_dispatch import _is_rag_fallback
    result_str = json.dumps([{"practice_id": "1", "score": 0.85}])
    assert _is_rag_fallback("search_practices", result_str) is False


def test_is_rag_fallback_empty_results():
    from Agent.Tools.tool_dispatch import _is_rag_fallback
    assert _is_rag_fallback("search_practices", "[]") is True


def test_is_rag_fallback_non_rag_tool():
    from Agent.Tools.tool_dispatch import _is_rag_fallback
    assert _is_rag_fallback("add_practice", "{}") is False
    assert _is_rag_fallback("list_facilitators", "[]") is False


# Alias pour approx (pytest disponible dans ce contexte)
try:
    from pytest import approx as pytest_approx
except ImportError:
    def pytest_approx(x, abs=0.01):
        return x
