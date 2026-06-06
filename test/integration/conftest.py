"""Fixtures partagées pour les tests d'intégration.

- Validation des clés API OpenAI et DeepSeek au démarrage
- Vérification de la collection ChromaDB locale
- Vérification de la disponibilité de weasyprint
- TestClient FastAPI avec provider mocké et DB isolée (tmp_path)
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from dotenv import load_dotenv

_BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BASE_DIR))

load_dotenv(_BASE_DIR / "Agent" / ".env")


def _validate_openai_key() -> bool:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return False
    try:
        from openai import OpenAI
        OpenAI(api_key=key).models.list()
        return True
    except Exception:
        return False


def _validate_deepseek_key() -> bool:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        return False
    try:
        from openai import OpenAI
        OpenAI(api_key=key, base_url="https://api.deepseek.com").models.list()
        return True
    except Exception:
        return False


def _check_rag_local() -> bool:
    try:
        import chromadb
        from Agent.Config.config import load_config, get_project_root
        cfg = load_config()
        chroma_path = str(get_project_root() / cfg["chroma_local"]["path"])
        collections = [c.name for c in chromadb.PersistentClient(path=chroma_path).list_collections()]
        return cfg["chroma_local"]["collection"] in collections
    except Exception:
        return False


def _check_weasyprint() -> bool:
    try:
        import weasyprint
        return True
    except Exception:
        return False


def pytest_sessionstart(session):
    openai_ok = _validate_openai_key()
    deepseek_ok = _validate_deepseek_key()
    rag_local_ok = _check_rag_local()
    weasyprint_ok = _check_weasyprint()

    session.config._openai_ok = openai_ok
    session.config._deepseek_ok = deepseek_ok
    session.config._rag_local_ok = rag_local_ok
    session.config._weasyprint_ok = weasyprint_ok
    session.config._llm_available = openai_ok or deepseek_ok

    print(f"\n{'='*55}")
    print(f"  🔑 OpenAI     : {'✓ disponible' if openai_ok else '✗ indisponible'}")
    print(f"  🔑 DeepSeek   : {'✓ disponible' if deepseek_ok else '✗ indisponible'}")
    print(f"  📚 RAG local  : {'✓ disponible' if rag_local_ok else '✗ indisponible'}")
    print(f"  📄 WeasyPrint : {'✓ disponible' if weasyprint_ok else '✗ indisponible'}")
    print(f"{'='*55}")

    if not openai_ok and not deepseek_ok:
        print("\n⚠️  Aucune clé API valide trouvée.")
        answer = input("  Voulez-vous continuer les tests sans les tests LLM ? [y/N] ")
        if answer.lower() != "y":
            pytest.exit("Tests d'intégration annulés par l'utilisateur.")
        print("  → Les tests LLM seront ignorés.\n")


def pytest_configure(config):
    config.addinivalue_line("markers", "openai: nécessite une clé API OpenAI valide")
    config.addinivalue_line("markers", "deepseek: nécessite une clé API DeepSeek valide")
    config.addinivalue_line("markers", "rag_local: nécessite la collection ChromaDB locale (init_rag --local)")
    config.addinivalue_line("markers", "weasyprint: nécessite weasyprint + dépendences système (libpango)")


@pytest.fixture(autouse=True)
def _skip_by_marker(request):
    if request.node.get_closest_marker("openai") and not request.config._openai_ok:
        pytest.skip("OpenAI API key non disponible")
    if request.node.get_closest_marker("deepseek") and not request.config._deepseek_ok:
        pytest.skip("DeepSeek API key non disponible")
    if request.node.get_closest_marker("rag_local") and not request.config._rag_local_ok:
        pytest.skip("Collection ChromaDB locale introuvable. Lancez : python -m Agent.Tools.RAG.init_rag --local")
    if request.node.get_closest_marker("weasyprint") and not request.config._weasyprint_ok:
        pytest.skip("WeasyPrint non disponible (libpango manquant)")


@pytest.fixture
def _mock_provider():
    """Crée un provider LLM mocké pour les tests d'interface web."""
    provider = MagicMock()
    provider.chat.return_value = (
        {"role": "assistant", "content": "Réponse de test. ||RÉSOLU||"},
        {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    provider._model = "gpt-4o"
    provider._router_model = "gpt-4o-mini"
    provider._simple_model = "gpt-4o-mini"
    provider._complex_model = "gpt-4o"
    return provider


@pytest.fixture
def client(tmp_path, _mock_provider):
    """TestClient FastAPI avec DB isolée (tmp_path) et provider LLM mocké."""
    db_file = os.path.join(str(tmp_path), "test_facilito.db")
    with patch("Agent.Tools.Database.schema._db_path", return_value=db_file):
        from Agent.Tools.Database.schema import init_db
        init_db()
        with patch("Agent.Main.main.build_provider", return_value=_mock_provider):
            from Agent.Main.main import create_app
            from fastapi.testclient import TestClient
            app = create_app("openai")
            yield TestClient(app)
