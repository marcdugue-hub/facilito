"""
Fixtures partagées pour tous les tests unitaires.

- isolated_db    : chaque test obtient une base SQLite temporaire vierge
- clear_rag_cache: vide le lru_cache de _get_collection entre les tests
- clear_memory   : réinitialise l'historique en mémoire de l'agent entre les tests
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Rend le répertoire racine du projet importable
sys.path.insert(0, str(Path(__file__).parents[2]))


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Redirige toutes les connexions SQLite vers un fichier temporaire isolé."""
    db_file = str(tmp_path / "test_facilito.db")
    with patch("Agent.Tools.Database.schema._db_path", return_value=db_file):
        from Agent.Tools.Database.schema import init_db
        init_db()
        yield db_file


@pytest.fixture(autouse=True)
def clear_rag_cache():
    """Vide le cache LRU du client Chroma entre les tests."""
    from Agent.Tools.RAG.search import _get_openai_collection, _get_local_collection
    _get_openai_collection.cache_clear()
    _get_local_collection.cache_clear()
    yield
    _get_openai_collection.cache_clear()
    _get_local_collection.cache_clear()


@pytest.fixture(autouse=True)
def clear_agent_memory():
    """Réinitialise l'historique conversationnel en mémoire entre les tests."""
    from Agent.Tools.Memory.store import _histories
    _histories.clear()
    yield
    _histories.clear()
