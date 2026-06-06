"""Tests d'intégration — Base de données SQLite.

Vérifie le bon fonctionnement de l'accès à la base de données :
- Schéma et création de tables
- Contraintes d'intégrité (clés étrangères)
- Workflows CRUD complexes
- Transactions et cohérence des données

Chaque test utilise une base isolée (tmp_path)."""
import os
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def _iso_db(tmp_path):
    db_file = os.path.join(str(tmp_path), "test_integration.db")
    with patch("Agent.Tools.Database.schema._db_path", return_value=db_file):
        from Agent.Tools.Database.schema import init_db
        init_db()
        yield


class TestSchema:
    def test_all_tables_created(self):
        from Agent.Tools.Database.schema import get_connection
        with get_connection() as conn:
            tables = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        expected = {"facilitators", "sessions", "participants", "session_participants",
                    "clients", "teams", "team_participants", "session_teams",
                    "session_clients", "session_practices", "agent_events",
                    "agent_ratings", "cost_config", "app_settings"}
        missing = expected - tables
        assert not missing, f"Tables manquantes : {missing}"

    def test_cost_config_defaults(self):
        from Agent.Tools.Database.schema import get_connection
        with get_connection() as conn:
            rows = dict(conn.execute("SELECT key, value FROM cost_config").fetchall())
        assert rows["cost_in"] == 1.5
        assert rows["cost_out"] == 2.5

    def test_app_settings_defaults(self):
        from Agent.Tools.Database.schema import get_connection
        with get_connection() as conn:
            rows = dict(conn.execute("SELECT key, value FROM app_settings").fetchall())
        assert rows["voice_mode"] == "off"


class TestForeignKeyConstraints:
    def test_session_cannot_have_nonexistent_facilitator(self):
        from Agent.Tools.Database.schema import get_connection
        with get_connection() as conn:
            try:
                conn.execute("INSERT INTO sessions (facilitator_id, title) VALUES (999, 'Test')")
                conn.commit()
                pytest.fail("Devrait lever une contrainte de clé étrangère")
            except Exception:
                pass

    def test_cascade_delete_facilitator_removes_sessions(self):
        from Agent.Tools.Database.facilitators import create_facilitator, delete_facilitator
        from Agent.Tools.Database.sessions import create_session, list_sessions
        fac = create_facilitator("À supprimer")
        create_session(fac["id"], "Session associée")
        assert len(list_sessions(fac["id"])) == 1
        delete_facilitator(fac["id"])
        assert len(list_sessions(fac["id"])) == 0


class TestWorkflows:
    def test_full_workflow(self):
        from Agent.Tools.Database.facilitators import create_facilitator
        from Agent.Tools.Database.sessions import create_session, add_practice_to_session, get_session_context
        from Agent.Tools.Database.participants import create_participant, add_participant_to_session

        fac = create_facilitator("Marc")
        assert fac["name"] == "Marc"

        sess = create_session(fac["id"], "Atelier OKR", "2026-09-01",
                              start_time="09:00", objective="Définir les OKR")
        assert sess["title"] == "Atelier OKR"
        assert sess["status"] == "draft"

        add_practice_to_session(sess["id"], "1", "Introduction", 15, "rag")
        add_practice_to_session(sess["id"], "2", "Définir OKR", 45, "rag")
        add_practice_to_session(sess["id"], "SPECIAL_PAUSE", "Pause", 10, "special")
        add_practice_to_session(sess["id"], "3", "Validation", 30, "rag")

        p1 = create_participant("Alice", "Dupont", "alice@co.com", "Manager")
        p2 = create_participant("Bob", "Martin", "bob@co.com", "Dev")
        add_participant_to_session(sess["id"], p1["id"])
        add_participant_to_session(sess["id"], p2["id"])

        ctx = get_session_context(sess["id"])
        assert ctx["total_duration"] == 100
        assert len(ctx["participants"]) == 2
        assert len(ctx["practices"]) == 4
        assert ctx["facilitator"]["name"] == "Marc"

    def test_multiple_facilitators_isolated(self):
        from Agent.Tools.Database.facilitators import create_facilitator
        from Agent.Tools.Database.sessions import create_session, list_sessions
        f1 = create_facilitator("Alice")
        f2 = create_facilitator("Bob")
        create_session(f1["id"], "Session A")
        create_session(f2["id"], "Session B")
        create_session(f2["id"], "Session C")
        assert len(list_sessions(f1["id"])) == 1
        assert len(list_sessions(f2["id"])) == 2

    def test_participant_can_be_in_multiple_sessions(self):
        from Agent.Tools.Database.facilitators import create_facilitator
        from Agent.Tools.Database.sessions import create_session
        from Agent.Tools.Database.participants import create_participant, add_participant_to_session, get_session_participants
        fac = create_facilitator("Test")
        s1 = create_session(fac["id"], "Session 1")
        s2 = create_session(fac["id"], "Session 2")
        p = create_participant("Multi", "Session")
        add_participant_to_session(s1["id"], p["id"])
        add_participant_to_session(s2["id"], p["id"])
        assert len(get_session_participants(s1["id"])) == 1
        assert len(get_session_participants(s2["id"])) == 1

    def test_event_logging(self):
        from Agent.Tools.Database.analytics import log_event, get_logs
        log_event(session_id=1, event_type="llm", summary="Test event",
                  payload='{"test": true}', tokens_in=10, tokens_out=5,
                  duration_ms=100)
        logs = get_logs(types=["llm"])
        assert len(logs) == 1
        assert logs[0]["tokens_in"] == 10
        assert logs[0]["summary"] == "Test event"

    def test_rating_storage(self):
        from Agent.Tools.Database.analytics import log_rating
        from Agent.Tools.Database.analytics import get_logs
        log_rating(1, 5)
        log_rating(1, 3)
        logs = get_logs(types=None, limit=100)
        ratings = [l for l in logs if l["event_type"] == "resolution"]
        # Les ratings sont stockés dans agent_ratings, pas agent_events
        from Agent.Tools.Database.schema import get_connection
        with get_connection() as conn:
            avg = conn.execute("SELECT AVG(rating) FROM agent_ratings WHERE session_id=1").fetchone()[0]
        assert avg == 4.0

    def test_team_participant_membership(self):
        from Agent.Tools.Database.clients_teams import create_team, add_participant_to_team, get_team_participants
        from Agent.Tools.Database.participants import create_participant
        team = create_team("Dev Team")
        p1 = create_participant("Alice", "Dev")
        p2 = create_participant("Bob", "Dev")
        add_participant_to_team(team["id"], p1["id"])
        add_participant_to_team(team["id"], p2["id"])
        members = get_team_participants(team["id"])
        assert len(members) == 2

    def test_add_practice_updates_position(self):
        from Agent.Tools.Database.facilitators import create_facilitator
        from Agent.Tools.Database.sessions import create_session, add_practice_to_session, get_session_practices
        fac = create_facilitator("PosTest")
        sess = create_session(fac["id"], "Positions")
        add_practice_to_session(sess["id"], "1", "Première", 10, "rag")
        add_practice_to_session(sess["id"], "2", "Deuxième", 20, "rag")
        practices = get_session_practices(sess["id"])
        assert practices[0]["position"] == 0
        assert practices[1]["position"] == 1

    def test_db_is_reinitializable(self):
        from Agent.Tools.Database.schema import init_db, get_connection
        init_db()
        with get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) as c FROM facilitators").fetchone()["c"]
            assert count == 0
