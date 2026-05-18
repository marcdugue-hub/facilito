"""Tests unitaires — Agent/Tools/Memory/store.py"""


def test_get_history_empty():
    from Agent.Tools.Memory.store import get_history
    assert get_history(1) == []


def test_add_message_user():
    from Agent.Tools.Memory.store import add_message, get_history
    add_message(1, "user", "Bonjour")
    history = get_history(1)
    assert len(history) == 1
    assert history[0] == {"role": "user", "content": "Bonjour"}


def test_add_message_assistant():
    from Agent.Tools.Memory.store import add_message, get_history
    add_message(1, "assistant", "Réponse")
    assert get_history(1)[0]["role"] == "assistant"


def test_histories_isolated_per_session():
    from Agent.Tools.Memory.store import add_message, get_history
    add_message(1, "user", "Session 1")
    add_message(2, "user", "Session 2")
    assert get_history(1)[0]["content"] == "Session 1"
    assert get_history(2)[0]["content"] == "Session 2"


def test_history_max_size_respected():
    from Agent.Tools.Memory.store import add_message, get_history, _MEMORY_SIZE
    for i in range(_MEMORY_SIZE + 5):
        add_message(99, "user", f"Message {i}")
    history = get_history(99)
    assert len(history) == _MEMORY_SIZE
    assert history[-1]["content"] == f"Message {_MEMORY_SIZE + 4}"


def test_clear_history():
    from Agent.Tools.Memory.store import add_message, clear, get_history
    add_message(1, "user", "Test")
    clear(1)
    assert get_history(1) == []


def test_add_raw_message():
    from Agent.Tools.Memory.store import add_raw_message, get_history
    msg = {"role": "assistant", "content": None, "tool_calls": [{"id": "x"}]}
    add_raw_message(1, msg)
    assert get_history(1)[0] == msg


# ── build_system_prompt ───────────────────────────────────────────────────────

def test_build_system_prompt_no_context_contains_role():
    from Agent.Tools.Memory.store import build_system_prompt
    prompt = build_system_prompt(None)
    assert "facilitat" in prompt.lower()


def test_build_system_prompt_no_context_contains_resolution_marker():
    from Agent.Tools.Memory.store import build_system_prompt
    prompt = build_system_prompt(None)
    assert "||RÉSOLU||" in prompt


def test_build_system_prompt_includes_session_id():
    from Agent.Tools.Memory.store import build_system_prompt
    ctx = {
        "id": 42, "title": "Mon Atelier", "date": "2026-07-01",
        "status": "confirmed", "objective": "Test", "total_duration": 90,
        "participants": [], "practices": [],
    }
    prompt = build_system_prompt(ctx)
    assert "42" in prompt


def test_build_system_prompt_includes_session_info():
    from Agent.Tools.Memory.store import build_system_prompt
    ctx = {
        "id": 1, "title": "Atelier Créativité", "date": "2026-07-01",
        "status": "draft", "objective": "Générer des idées", "total_duration": 60,
        "participants": [], "practices": [],
    }
    prompt = build_system_prompt(ctx)
    assert "Atelier Créativité" in prompt
    assert "Générer des idées" in prompt
    assert "60" in prompt


def test_build_system_prompt_includes_participants():
    from Agent.Tools.Memory.store import build_system_prompt
    ctx = {
        "id": 1, "title": "T", "date": None, "status": "draft",
        "objective": None, "total_duration": 0,
        "participants": [
            {"first_name": "Alice", "last_name": "Martin", "role": "Dev"},
            {"first_name": "Bob", "last_name": "Dupont", "role": None},
        ],
        "practices": [],
    }
    prompt = build_system_prompt(ctx)
    assert "Alice Martin" in prompt
    assert "Dev" in prompt
    assert "Bob Dupont" in prompt


def test_build_system_prompt_includes_practices():
    from Agent.Tools.Memory.store import build_system_prompt
    ctx = {
        "id": 1, "title": "T", "date": None, "status": "draft",
        "objective": None, "total_duration": 45,
        "participants": [],
        "practices": [
            {"id": 10, "titre": "Brainstorming", "duration_minutes": 45, "source": "rag"},
        ],
    }
    prompt = build_system_prompt(ctx)
    assert "Brainstorming" in prompt
    assert "45" in prompt
