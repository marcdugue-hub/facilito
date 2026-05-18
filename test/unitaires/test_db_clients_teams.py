"""Tests unitaires — Agent/Tools/Database/clients_teams.py"""


# ── Clients ───────────────────────────────────────────────────────────────────

def test_create_client():
    from Agent.Tools.Database.clients_teams import create_client
    c = create_client("Acme Corp")
    assert c["name"] == "Acme Corp"
    assert isinstance(c["id"], int)


def test_list_clients_empty():
    from Agent.Tools.Database.clients_teams import list_clients
    assert list_clients() == []


def test_list_clients_returns_all():
    from Agent.Tools.Database.clients_teams import create_client, list_clients
    create_client("Alpha")
    create_client("Beta")
    names = {c["name"] for c in list_clients()}
    assert names == {"Alpha", "Beta"}


def test_get_client_existing():
    from Agent.Tools.Database.clients_teams import create_client, get_client
    c = create_client("Acme")
    found = get_client(c["id"])
    assert found["name"] == "Acme"


def test_get_client_not_found():
    from Agent.Tools.Database.clients_teams import get_client
    assert get_client(9999) is None


# ── Teams ─────────────────────────────────────────────────────────────────────

def test_create_team_without_client():
    from Agent.Tools.Database.clients_teams import create_team
    t = create_team("Equipe RH")
    assert t["name"] == "Equipe RH"
    assert t["client_id"] is None


def test_create_team_with_client():
    from Agent.Tools.Database.clients_teams import create_client, create_team
    c = create_client("Acme")
    t = create_team("RH", client_id=c["id"])
    assert t["client_id"] == c["id"]


def test_list_teams_all():
    from Agent.Tools.Database.clients_teams import create_team, list_teams
    create_team("A")
    create_team("B")
    assert len(list_teams()) == 2


def test_list_teams_filtered_by_client():
    from Agent.Tools.Database.clients_teams import create_client, create_team, list_teams
    c1 = create_client("Client 1")
    c2 = create_client("Client 2")
    create_team("Team C1", client_id=c1["id"])
    create_team("Team C2", client_id=c2["id"])
    result = list_teams(client_id=c1["id"])
    assert len(result) == 1
    assert result[0]["name"] == "Team C1"


def test_get_team_existing():
    from Agent.Tools.Database.clients_teams import create_team, get_team
    t = create_team("RH")
    assert get_team(t["id"])["name"] == "RH"


def test_get_team_not_found():
    from Agent.Tools.Database.clients_teams import get_team
    assert get_team(9999) is None


# ── Team membership ───────────────────────────────────────────────────────────

def test_add_participant_to_team():
    from Agent.Tools.Database.clients_teams import create_team, add_participant_to_team, get_team_participants
    from Agent.Tools.Database.participants import create_participant
    t = create_team("RH")
    p = create_participant("Alice", "M")
    result = add_participant_to_team(t["id"], p["id"])
    assert result is True
    assert len(get_team_participants(t["id"])) == 1


def test_add_participant_to_team_idempotent():
    from Agent.Tools.Database.clients_teams import create_team, add_participant_to_team
    from Agent.Tools.Database.participants import create_participant
    t = create_team("RH")
    p = create_participant("Alice", "M")
    add_participant_to_team(t["id"], p["id"])
    result = add_participant_to_team(t["id"], p["id"])
    assert result is False


def test_remove_participant_from_team():
    from Agent.Tools.Database.clients_teams import (
        create_team, add_participant_to_team, remove_participant_from_team, get_team_participants,
    )
    from Agent.Tools.Database.participants import create_participant
    t = create_team("RH")
    p = create_participant("Alice", "M")
    add_participant_to_team(t["id"], p["id"])
    remove_participant_from_team(t["id"], p["id"])
    assert get_team_participants(t["id"]) == []


def test_get_team_participants_empty():
    from Agent.Tools.Database.clients_teams import create_team, get_team_participants
    t = create_team("RH")
    assert get_team_participants(t["id"]) == []
