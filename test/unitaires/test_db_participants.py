"""Tests unitaires — Agent/Tools/Database/participants.py"""
import pytest


@pytest.fixture
def sess():
    from Agent.Tools.Database.facilitators import create_facilitator
    from Agent.Tools.Database.sessions import create_session
    fac = create_facilitator("Fac")
    return create_session(fac["id"], "Session")


# ── create / list / get ───────────────────────────────────────────────────────

def test_create_participant_full():
    from Agent.Tools.Database.participants import create_participant
    p = create_participant("Alice", "Martin", "alice@test.com", "Dev")
    assert p["first_name"] == "Alice"
    assert p["last_name"] == "Martin"
    assert p["email"] == "alice@test.com"
    assert p["role"] == "Dev"


def test_create_participant_minimal():
    from Agent.Tools.Database.participants import create_participant
    p = create_participant("Bob", "Dupont")
    assert p["email"] is None
    assert p["role"] is None


def test_list_participants_empty():
    from Agent.Tools.Database.participants import list_participants
    assert list_participants() == []


def test_list_participants_returns_all():
    from Agent.Tools.Database.participants import create_participant, list_participants
    create_participant("Alice", "M")
    create_participant("Bob", "D")
    assert len(list_participants()) == 2


def test_get_participant_existing():
    from Agent.Tools.Database.participants import create_participant, get_participant
    p = create_participant("Alice", "M")
    found = get_participant(p["id"])
    assert found["first_name"] == "Alice"


def test_get_participant_not_found():
    from Agent.Tools.Database.participants import get_participant
    assert get_participant(9999) is None


# ── session membership ────────────────────────────────────────────────────────

def test_add_participant_to_session(sess):
    from Agent.Tools.Database.participants import create_participant, add_participant_to_session, get_session_participants
    p = create_participant("Alice", "M")
    result = add_participant_to_session(sess["id"], p["id"])
    assert result is True
    members = get_session_participants(sess["id"])
    assert len(members) == 1
    assert members[0]["first_name"] == "Alice"


def test_add_participant_to_session_idempotent(sess):
    from Agent.Tools.Database.participants import create_participant, add_participant_to_session
    p = create_participant("Alice", "M")
    add_participant_to_session(sess["id"], p["id"])
    result = add_participant_to_session(sess["id"], p["id"])
    assert result is False


def test_remove_participant_from_session(sess):
    from Agent.Tools.Database.participants import (
        create_participant, add_participant_to_session,
        remove_participant_from_session, get_session_participants,
    )
    p = create_participant("Alice", "M")
    add_participant_to_session(sess["id"], p["id"])
    remove_participant_from_session(sess["id"], p["id"])
    assert get_session_participants(sess["id"]) == []


def test_get_session_participants_empty(sess):
    from Agent.Tools.Database.participants import get_session_participants
    assert get_session_participants(sess["id"]) == []


def test_get_session_participants_sorted_by_name(sess):
    from Agent.Tools.Database.participants import (
        create_participant, add_participant_to_session, get_session_participants,
    )
    p_z = create_participant("Zoé", "Martin")
    p_a = create_participant("Alice", "Dupont")
    add_participant_to_session(sess["id"], p_z["id"])
    add_participant_to_session(sess["id"], p_a["id"])
    members = get_session_participants(sess["id"])
    assert members[0]["last_name"] == "Dupont"
