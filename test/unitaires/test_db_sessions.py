"""Tests unitaires — Agent/Tools/Database/sessions.py"""
import pytest


@pytest.fixture
def fac():
    from Agent.Tools.Database.facilitators import create_facilitator
    return create_facilitator("Facilitateur Test")


@pytest.fixture
def sess(fac):
    from Agent.Tools.Database.sessions import create_session
    return create_session(fac["id"], "Session Test", "2026-06-15", "Objectif de test")


# ── create_session ────────────────────────────────────────────────────────────

def test_create_session_default_status(fac):
    from Agent.Tools.Database.sessions import create_session
    s = create_session(fac["id"], "Atelier")
    assert s["status"] == "draft"
    assert s["facilitator_id"] == fac["id"]


def test_create_session_with_all_fields(fac):
    from Agent.Tools.Database.sessions import create_session
    s = create_session(fac["id"], "Atelier", date="2026-07-01", objective="Créer une charte")
    assert s["title"] == "Atelier"
    assert s["date"] == "2026-07-01"
    assert s["objective"] == "Créer une charte"


# ── get / update / delete session ─────────────────────────────────────────────

def test_get_session_existing(sess):
    from Agent.Tools.Database.sessions import get_session
    found = get_session(sess["id"])
    assert found is not None
    assert found["id"] == sess["id"]


def test_get_session_not_found():
    from Agent.Tools.Database.sessions import get_session
    assert get_session(9999) is None


def test_update_session_title(sess):
    from Agent.Tools.Database.sessions import update_session
    updated = update_session(sess["id"], title="Nouveau titre")
    assert updated["title"] == "Nouveau titre"


def test_update_session_status(sess):
    from Agent.Tools.Database.sessions import update_session
    updated = update_session(sess["id"], status="confirmed")
    assert updated["status"] == "confirmed"


def test_update_session_ignores_unknown_fields(sess):
    from Agent.Tools.Database.sessions import update_session, get_session
    update_session(sess["id"], title="OK")
    found = get_session(sess["id"])
    assert found["title"] == "OK"


def test_delete_session_removes_it(sess):
    from Agent.Tools.Database.sessions import delete_session, get_session
    delete_session(sess["id"])
    assert get_session(sess["id"]) is None


# ── list_sessions ─────────────────────────────────────────────────────────────

def test_list_sessions_only_own(fac):
    from Agent.Tools.Database.facilitators import create_facilitator
    from Agent.Tools.Database.sessions import create_session, list_sessions
    other = create_facilitator("Autre")
    create_session(fac["id"], "Ma session")
    create_session(other["id"], "Autre session")
    assert len(list_sessions(fac["id"])) == 1


# ── get_session_context ───────────────────────────────────────────────────────

def test_get_session_context_includes_facilitator(sess):
    from Agent.Tools.Database.sessions import get_session_context
    ctx = get_session_context(sess["id"])
    assert ctx["facilitator"]["name"] == "Facilitateur Test"


def test_get_session_context_computes_total_duration(fac):
    from Agent.Tools.Database.sessions import create_session, add_practice_to_session, get_session_context
    s = create_session(fac["id"], "Test")
    add_practice_to_session(s["id"], "1", "Pratique A", 30, "rag")
    add_practice_to_session(s["id"], "2", "Pratique B", 45, "rag")
    ctx = get_session_context(s["id"])
    assert ctx["total_duration"] == 75


def test_get_session_context_not_found():
    from Agent.Tools.Database.sessions import get_session_context
    assert get_session_context(9999) is None


# ── add / remove practice ─────────────────────────────────────────────────────

def test_add_practice_appends_to_end(sess):
    from Agent.Tools.Database.sessions import add_practice_to_session, get_session_practices
    add_practice_to_session(sess["id"], "1", "Première", 30, "rag")
    add_practice_to_session(sess["id"], "2", "Deuxième", 20, "rag")
    practices = get_session_practices(sess["id"])
    assert practices[0]["titre"] == "Première"
    assert practices[1]["titre"] == "Deuxième"
    assert practices[0]["position"] == 0
    assert practices[1]["position"] == 1


def test_add_special_practice(sess):
    from Agent.Tools.Database.sessions import add_practice_to_session, get_session_practices
    add_practice_to_session(sess["id"], "SPECIAL_PAUSE", "Pause", 10, "special")
    practices = get_session_practices(sess["id"])
    assert practices[0]["source"] == "special"


def test_remove_practice_decrements_positions(sess):
    from Agent.Tools.Database.sessions import add_practice_to_session, remove_practice_from_session, get_session_practices
    p1 = add_practice_to_session(sess["id"], "1", "A", 10, "rag")
    p2 = add_practice_to_session(sess["id"], "2", "B", 20, "rag")
    add_practice_to_session(sess["id"], "3", "C", 30, "rag")
    remove_practice_from_session(sess["id"], p1["id"])
    practices = get_session_practices(sess["id"])
    assert len(practices) == 2
    assert practices[0]["position"] == 0


def test_remove_practice_not_in_session_returns_false(sess):
    from Agent.Tools.Database.sessions import remove_practice_from_session
    assert remove_practice_from_session(sess["id"], 9999) is False


# ── reorder_practice ──────────────────────────────────────────────────────────

def test_reorder_practice_up(sess):
    from Agent.Tools.Database.sessions import add_practice_to_session, reorder_practice
    add_practice_to_session(sess["id"], "1", "A", 10, "rag")
    p2 = add_practice_to_session(sess["id"], "2", "B", 20, "rag")
    result = reorder_practice(sess["id"], p2["id"], "up")
    assert result[0]["titre"] == "B"
    assert result[1]["titre"] == "A"


def test_reorder_practice_down(sess):
    from Agent.Tools.Database.sessions import add_practice_to_session, reorder_practice
    p1 = add_practice_to_session(sess["id"], "1", "A", 10, "rag")
    add_practice_to_session(sess["id"], "2", "B", 20, "rag")
    result = reorder_practice(sess["id"], p1["id"], "down")
    assert result[0]["titre"] == "B"
    assert result[1]["titre"] == "A"


def test_reorder_first_up_noop(sess):
    from Agent.Tools.Database.sessions import add_practice_to_session, reorder_practice
    p1 = add_practice_to_session(sess["id"], "1", "A", 10, "rag")
    add_practice_to_session(sess["id"], "2", "B", 20, "rag")
    result = reorder_practice(sess["id"], p1["id"], "up")
    assert result[0]["titre"] == "A"


# ── update_practice_duration ──────────────────────────────────────────────────

def test_update_practice_duration(sess):
    from Agent.Tools.Database.sessions import add_practice_to_session, update_practice_duration
    p = add_practice_to_session(sess["id"], "1", "Pratique", 30, "rag")
    updated = update_practice_duration(sess["id"], p["id"], 60)
    assert updated["duration_minutes"] == 60


# ── add_team_to_session ───────────────────────────────────────────────────────

def test_add_team_to_session_imports_all_members(fac):
    from Agent.Tools.Database.sessions import create_session, add_team_to_session
    from Agent.Tools.Database.clients_teams import create_team, add_participant_to_team
    from Agent.Tools.Database.participants import create_participant, get_session_participants
    sess = create_session(fac["id"], "Test")
    team = create_team("Equipe A")
    p1 = create_participant("Alice", "M")
    p2 = create_participant("Bob", "D")
    add_participant_to_team(team["id"], p1["id"])
    add_participant_to_team(team["id"], p2["id"])
    added = add_team_to_session(sess["id"], team["id"])
    assert added == 2
    assert len(get_session_participants(sess["id"])) == 2


def test_add_team_to_session_idempotent(fac):
    from Agent.Tools.Database.sessions import create_session, add_team_to_session
    from Agent.Tools.Database.clients_teams import create_team, add_participant_to_team
    from Agent.Tools.Database.participants import create_participant, get_session_participants
    sess = create_session(fac["id"], "Test")
    team = create_team("Equipe")
    p = create_participant("Alice", "M")
    add_participant_to_team(team["id"], p["id"])
    add_team_to_session(sess["id"], team["id"])
    add_team_to_session(sess["id"], team["id"])  # second call
    assert len(get_session_participants(sess["id"])) == 1
