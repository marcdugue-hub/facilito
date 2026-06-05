"""
Tests unitaires — boucle agent (Agent/Main/main.py : agent_chat + _dispatch_tool).
Le LLM est mocké avec des réponses statiques. La base SQLite utilise le DB temporaire
de l'isolated_db fixture (conftest.py).
"""
import json
import pytest
from unittest.mock import patch, MagicMock


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _static_llm_response(content="Réponse de test. ||RÉSOLU||", tool_calls=None,
                          tokens_in=20, tokens_out=10):
    """Retourne un tuple (message_dict, usage_dict) simulant une réponse LLM."""
    return (
        {"role": "assistant", "content": content, "tool_calls": tool_calls},
        {"prompt_tokens": tokens_in, "completion_tokens": tokens_out,
         "total_tokens": tokens_in + tokens_out},
    )


def _tool_call(name, args, call_id="call_001"):
    """Crée un tool_call dict au format OpenAI."""
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.chat.return_value = _static_llm_response()
    provider._model = "gpt-4o"
    provider._router_model = "gpt-4o-mini"
    provider._simple_model = "gpt-4o-mini"
    provider._complex_model = "gpt-4o"
    return provider


@pytest.fixture
def client(mock_provider):
    """Crée un TestClient FastAPI avec LLM mocké."""
    with patch("Agent.Main.main._build_provider", return_value=mock_provider):
        from Agent.Main.main import create_app
        from fastapi.testclient import TestClient
        app = create_app("openai")
        return TestClient(app)


@pytest.fixture
def session_in_db():
    """Crée un facilitateur et une session dans la DB de test."""
    from Agent.Tools.Database.facilitators import create_facilitator
    from Agent.Tools.Database.sessions import create_session
    fac = create_facilitator("Fac Test")
    sess = create_session(fac["id"], "Session Test", "2026-07-01", "Test")
    return {"facilitator": fac, "session": sess}


# ── Tests réponse texte simple ────────────────────────────────────────────────

def test_agent_chat_simple_response(client):
    """L'agent retourne un texte sans appeler d'outil."""
    response = client.post("/api/agent/chat", json={"session_id": 0, "message": "Bonjour"})
    assert response.status_code == 200
    data = response.json()
    assert "Réponse de test" in data["reply"]
    assert data["tool_results"] == []


def test_agent_chat_strips_resolu_marker(client):
    """Le marqueur ||RÉSOLU|| est retiré de la réponse affichée."""
    response = client.post("/api/agent/chat", json={"session_id": 0, "message": "Test"})
    data = response.json()
    assert "||RÉSOLU||" not in data["reply"]
    assert "||NON_RÉSOLU||" not in data["reply"]


def test_agent_chat_strips_non_resolu_marker(client, mock_provider):
    """Le marqueur ||NON_RÉSOLU|| est retiré de la réponse affichée."""
    mock_provider.chat.return_value = _static_llm_response("Impossible. ||NON_RÉSOLU||")
    response = client.post("/api/agent/chat", json={"session_id": 0, "message": "Test"})
    data = response.json()
    assert "||NON_RÉSOLU||" not in data["reply"]
    assert "Impossible" in data["reply"]


# ── Tests appel d'outil RAG ───────────────────────────────────────────────────

def test_agent_chat_calls_rag_tool(client, mock_provider):
    """L'agent appelle search_practices, obtient des résultats, puis répond."""
    tc = _tool_call("search_practices", {"query": "icebreaker", "n_results": 3})
    _routing = _static_llm_response(content="Simple")
    mock_provider.chat.side_effect = [
        _routing,
        _static_llm_response(tool_calls=[tc], content=None),
        _static_llm_response("J'ai trouvé des pratiques. ||RÉSOLU||"),
    ]
    rag_results = [{"practice_id": "1", "titre": "Matrice DIXIT", "categorie": "Briser la glace",
                    "score": 0.9, "duration_minutes": 30, "phase": "Ouverture",
                    "difficulte": "Facile", "duree": "30'", "participants": "10-50",
                    "icone_code": "ICE01", "url": "", "objectif": "Test", "resume": "Test"}]
    with patch("Agent.Main.main.search_practices", return_value=rag_results):
        response = client.post("/api/agent/chat",
                               json={"session_id": 0, "message": "Propose un icebreaker"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["tool_results"]) == 1
    assert data["tool_results"][0]["tool"] == "search_practices"
    assert "trouvé" in data["reply"]


# ── Test injection session_id ────────────────────────────────────────────────

def test_agent_session_id_injected_even_if_llm_wrong(client, mock_provider, session_in_db):
    """Même si le LLM fournit un mauvais session_id, le bon est injecté côté serveur."""
    sess_id = session_in_db["session"]["id"]
    wrong_id = 9999

    tc = _tool_call("add_practice", {
        "session_id": wrong_id,   # LLM utilise un mauvais ID
        "practice_id": "1",
        "titre": "Brainstorming",
        "duration_minutes": 45,
        "source": "rag",
    })
    _routing = _static_llm_response(content="Simple")
    mock_provider.chat.side_effect = [
        _routing,
        _static_llm_response(tool_calls=[tc], content=None),
        _static_llm_response("Pratique ajoutée ! ||RÉSOLU||"),
    ]

    response = client.post("/api/agent/chat",
                           json={"session_id": sess_id, "message": "Ajoute Brainstorming"})
    assert response.status_code == 200

    from Agent.Tools.Database.sessions import get_session_practices
    practices = get_session_practices(sess_id)
    assert len(practices) == 1
    assert practices[0]["titre"] == "Brainstorming"


# ── Test gestion d'erreur outil ───────────────────────────────────────────────

def test_agent_tool_error_does_not_cause_500(client, mock_provider):
    """Une exception dans un outil retourne une erreur JSON à l'agent, pas un 500."""
    tc = _tool_call("add_practice", {
        # session_id=0 sera injecté → foreign key error sur la DB vide
        "practice_id": "1", "titre": "Test", "duration_minutes": 30, "source": "rag",
    })
    _routing = _static_llm_response(content="Simple")
    mock_provider.chat.side_effect = [
        _routing,
        _static_llm_response(tool_calls=[tc], content=None),
        _static_llm_response("Erreur gérée. ||NON_RÉSOLU||"),
    ]
    response = client.post("/api/agent/chat", json={"session_id": 0, "message": "Test"})
    assert response.status_code == 200


# ── Test historique conversationnel ──────────────────────────────────────────

def test_agent_history_stored_after_exchange(client):
    """L'historique user+assistant est stocké après chaque échange."""
    client.post("/api/agent/chat", json={"session_id": 77, "message": "Premier message"})
    from Agent.Tools.Memory.store import get_history
    history = get_history(77)
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "Premier message"}
    assert history[1]["role"] == "assistant"


def test_agent_history_accumulates(client, mock_provider):
    """Les échanges successifs s'accumulent dans l'historique."""
    client.post("/api/agent/chat", json={"session_id": 88, "message": "Message 1"})
    client.post("/api/agent/chat", json={"session_id": 88, "message": "Message 2"})
    from Agent.Tools.Memory.store import get_history
    history = get_history(88)
    assert len(history) == 4  # 2 × (user + assistant)


# ── Tests logs analytics ──────────────────────────────────────────────────────

def test_agent_logs_llm_event(client):
    """Chaque appel LLM est loggé dans agent_events."""
    client.post("/api/agent/chat", json={"session_id": 0, "message": "Test"})
    from Agent.Tools.Database.analytics import get_logs
    llm_logs = get_logs(types=["llm"])
    assert len(llm_logs) >= 1
    assert llm_logs[0]["tokens_in"] == 20
    assert llm_logs[0]["tokens_out"] == 10


def test_agent_logs_resolution_event(client):
    """Un événement resolution est loggé à la fin de chaque échange."""
    client.post("/api/agent/chat", json={"session_id": 0, "message": "Test"})
    from Agent.Tools.Database.analytics import get_logs
    res_logs = get_logs(types=["resolution"])
    assert len(res_logs) == 1
    assert res_logs[0]["resolved"] == 1  # ||RÉSOLU|| → True


def test_agent_logs_non_resolu_as_false(client, mock_provider):
    """||NON_RÉSOLU|| est loggé resolved=0."""
    mock_provider.chat.return_value = _static_llm_response("Pas pu. ||NON_RÉSOLU||")
    client.post("/api/agent/chat", json={"session_id": 0, "message": "Test"})
    from Agent.Tools.Database.analytics import get_logs
    res_logs = get_logs(types=["resolution"])
    assert res_logs[0]["resolved"] == 0


def test_agent_logs_rag_event_when_rag_tool_called(client, mock_provider):
    """Un appel à search_practices est loggé comme event_type='rag'."""
    tc = _tool_call("search_practices", {"query": "test"})
    _routing = _static_llm_response(content="Simple")
    mock_provider.chat.side_effect = [
        _routing,
        _static_llm_response(tool_calls=[tc], content=None),
        _static_llm_response("Résultat. ||RÉSOLU||"),
    ]
    with patch("Agent.Main.main.search_practices", return_value=[]):
        client.post("/api/agent/chat", json={"session_id": 0, "message": "Cherche"})
    from Agent.Tools.Database.analytics import get_logs
    rag_logs = get_logs(types=["rag"])
    assert len(rag_logs) == 1


# ── Tests _dispatch_tool directement ────────────────────────────────────────

def test_dispatch_list_facilitators_empty():
    from Agent.Main.main import _dispatch_tool
    result = json.loads(_dispatch_tool("list_facilitators", {}))
    assert result == []


def test_dispatch_list_facilitators_with_data():
    from Agent.Tools.Database.facilitators import create_facilitator
    from Agent.Main.main import _dispatch_tool
    create_facilitator("Alice")
    result = json.loads(_dispatch_tool("list_facilitators", {}))
    assert len(result) == 1
    assert result[0]["name"] == "Alice"


def test_dispatch_unknown_tool_returns_error():
    from Agent.Main.main import _dispatch_tool
    result = json.loads(_dispatch_tool("unknown_tool_xyz", {}))
    assert "error" in result


def test_dispatch_create_client():
    from Agent.Main.main import _dispatch_tool
    result = json.loads(_dispatch_tool("create_client", {"name": "Acme Corp"}))
    assert result["name"] == "Acme Corp"
    assert "id" in result


def test_dispatch_create_session(session_in_db):
    from Agent.Main.main import _dispatch_tool
    fac_id = session_in_db["facilitator"]["id"]
    result = json.loads(_dispatch_tool("create_session", {
        "facilitator_id": fac_id,
        "title": "Nouvel Atelier",
    }))
    assert result["title"] == "Nouvel Atelier"
    assert result["status"] == "draft"


# ── Tests list_sessions ────────────────────────────────────────────────────

def test_dispatch_list_sessions_empty():
    from Agent.Main.main import _dispatch_tool
    result = json.loads(_dispatch_tool("list_sessions", {}))
    assert result == []


def test_dispatch_list_sessions_all():
    from Agent.Tools.Database.facilitators import create_facilitator
    from Agent.Tools.Database.sessions import create_session
    from Agent.Main.main import _dispatch_tool
    fac = create_facilitator("Alice")
    create_session(fac["id"], "Session A", "2026-07-01", objective="Obj A")
    create_session(fac["id"], "Session B", "2026-07-02", objective="Obj B")
    result = json.loads(_dispatch_tool("list_sessions", {}))
    assert len(result) == 2
    assert result[0]["title"] == "Session B"  # plus récente d'abord


def test_dispatch_list_sessions_filtered_by_facilitator():
    from Agent.Tools.Database.facilitators import create_facilitator
    from Agent.Tools.Database.sessions import create_session
    from Agent.Main.main import _dispatch_tool
    fac_a = create_facilitator("Alice")
    fac_b = create_facilitator("Bob")
    create_session(fac_a["id"], "Session A1", "2026-07-01")
    create_session(fac_a["id"], "Session A2", "2026-07-02")
    create_session(fac_b["id"], "Session B1", "2026-07-01")
    result = json.loads(_dispatch_tool("list_sessions", {"facilitator_id": fac_a["id"]}))
    assert len(result) == 2
    assert all(s["title"].startswith("Session A") for s in result)


# ── Tests REST API — list sessions ─────────────────────────────────────────

def test_rest_list_sessions_by_facilitator(client):
    from Agent.Tools.Database.facilitators import create_facilitator
    from Agent.Tools.Database.sessions import create_session
    fac = create_facilitator("Alice")
    create_session(fac["id"], "Session 1", "2026-07-01")
    create_session(fac["id"], "Session 2", "2026-07-02")
    response = client.get(f"/api/facilitators/{fac['id']}/sessions")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["facilitator_name"] == "Alice"


def test_rest_list_sessions_empty_facilitator(client):
    from Agent.Tools.Database.facilitators import create_facilitator
    fac = create_facilitator("Bob")
    response = client.get(f"/api/facilitators/{fac['id']}/sessions")
    assert response.status_code == 200
    assert response.json() == []


# ── Tests REST API — create session with all fields ─────────────────────────

def test_rest_create_session_with_start_time_and_objective(client):
    from Agent.Tools.Database.facilitators import create_facilitator
    fac = create_facilitator("Marc")
    response = client.post("/api/sessions", json={
        "facilitator_id": fac["id"],
        "title": "Atelier OKR",
        "date": "2026-06-09",
        "start_time": "14:00",
        "objective": "Réorganiser la DSI autour de pratiques IA et OKR",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["start_time"] == "14:00"
    assert data["objective"] == "Réorganiser la DSI autour de pratiques IA et OKR"
    assert data["date"] == "2026-06-09"


def test_rest_create_session_minimal(client):
    from Agent.Tools.Database.facilitators import create_facilitator
    fac = create_facilitator("Marc")
    response = client.post("/api/sessions", json={
        "facilitator_id": fac["id"],
        "title": "Minimal",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Minimal"
    assert data["start_time"] is None
    assert data["objective"] is None


# ── Tests agent list_sessions tool call ─────────────────────────────────────

def test_agent_calls_list_sessions_tool(client, mock_provider):
    """L'agent appelle list_sessions quand l'utilisateur demande ses sessions."""
    from Agent.Tools.Database.facilitators import create_facilitator
    from Agent.Tools.Database.sessions import create_session
    fac = create_facilitator("Fac Test")
    create_session(fac["id"], "Session Test", "2026-07-01", objective="Test")

    tc = _tool_call("list_sessions", {})
    _routing = _static_llm_response(content="Simple")
    mock_provider.chat.side_effect = [
        _routing,
        _static_llm_response(tool_calls=[tc], content=None),
        _static_llm_response("Voici les sessions. ||RÉSOLU||"),
    ]
    response = client.post("/api/agent/chat",
                           json={"session_id": 0, "message": "Quelles sont mes sessions ?"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["tool_results"]) == 1
    assert data["tool_results"][0]["tool"] == "list_sessions"
    assert "session" in data["reply"].lower()


def test_agent_calls_list_sessions_filtered_by_facilitator(client, mock_provider):
    """L'agent appelle list_sessions avec un facilitator_id quand demandé."""
    from Agent.Tools.Database.facilitators import create_facilitator
    from Agent.Tools.Database.sessions import create_session
    fac = create_facilitator("Alice")
    create_session(fac["id"], "Session Alice", "2026-07-01", objective="Test")

    tc = _tool_call("list_sessions", {"facilitator_id": fac["id"]})
    _routing = _static_llm_response(content="Simple")
    mock_provider.chat.side_effect = [
        _routing,
        _static_llm_response(tool_calls=[tc], content=None),
        _static_llm_response("Voici les sessions d'Alice. ||RÉSOLU||"),
    ]
    response = client.post("/api/agent/chat",
                           json={"session_id": 0, "message": "Liste les sessions d'Alice"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["tool_results"]) == 1
    assert data["tool_results"][0]["tool"] == "list_sessions"
    # Vérifie que le bon facilitator_id a été passé à l'outil
    assert data["tool_results"][0]["args"]["facilitator_id"] == fac["id"]
