"""Tests d'intégration — Interface web (FastAPI + SPA).

Vérifie que le serveur FastAPI sert correctement :
- Les fichiers statiques (HTML, JS, CSS, images)
- Les endpoints REST (CRUD)
- La boucle agent (avec provider mocké)

Chaque test reçoit un client frais avec DB isolée et LLM mocké."""
from unittest.mock import patch
import pytest


class TestStaticFiles:
    def test_root_endpoint(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_index_html(self, client):
        response = client.get("/static/index.html")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_app_js(self, client):
        response = client.get("/static/app.js")
        assert response.status_code == 200
        assert "text" in response.headers["content-type"]

    def test_style_css(self, client):
        response = client.get("/static/style.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]

    def test_mascots_list(self, client):
        response = client.get("/api/mascots")
        assert response.status_code == 200
        mascots = response.json()
        assert isinstance(mascots, list)
        assert len(mascots) > 0


class TestFacilitatorsAPI:
    def test_list_facilitators_empty(self, client):
        response = client.get("/api/facilitators")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_facilitator(self, client):
        response = client.post("/api/facilitators", json={"name": "Alice"})
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Alice"
        assert "id" in data

    def test_get_facilitator(self, client):
        created = client.post("/api/facilitators", json={"name": "Bob"}).json()
        response = client.get(f"/api/facilitators/{created['id']}")
        assert response.status_code == 200
        assert response.json()["name"] == "Bob"

    def test_get_facilitator_not_found(self, client):
        response = client.get("/api/facilitators/99999")
        assert response.status_code == 404

    def test_delete_facilitator(self, client):
        created = client.post("/api/facilitators", json={"name": "Charlie"}).json()
        response = client.delete(f"/api/facilitators/{created['id']}")
        assert response.status_code == 204
        assert client.get(f"/api/facilitators/{created['id']}").status_code == 404


class TestSessionsAPI:
    def test_create_session(self, client):
        fac = client.post("/api/facilitators", json={"name": "SessionTest"}).json()
        response = client.post("/api/sessions", json={
            "facilitator_id": fac["id"],
            "title": "Mon Atelier",
            "date": "2026-07-01",
            "start_time": "09:00",
            "objective": "Créer une vision commune",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Mon Atelier"
        assert data["start_time"] == "09:00"
        assert data["status"] == "draft"

    def test_get_session(self, client):
        fac = client.post("/api/facilitators", json={"name": "GetTest"}).json()
        created = client.post("/api/sessions", json={
            "facilitator_id": fac["id"], "title": "Test",
        }).json()
        response = client.get(f"/api/sessions/{created['id']}")
        assert response.status_code == 200
        assert response.json()["title"] == "Test"

    def test_update_session(self, client):
        fac = client.post("/api/facilitators", json={"name": "UpdTest"}).json()
        created = client.post("/api/sessions", json={
            "facilitator_id": fac["id"], "title": "Avant",
        }).json()
        response = client.patch(f"/api/sessions/{created['id']}", json={
            "title": "Après", "status": "confirmed",
        })
        assert response.status_code == 200
        assert response.json()["title"] == "Après"
        assert response.json()["status"] == "confirmed"

    def test_delete_session(self, client):
        fac = client.post("/api/facilitators", json={"name": "DelTest"}).json()
        created = client.post("/api/sessions", json={
            "facilitator_id": fac["id"], "title": "À supprimer",
        }).json()
        response = client.delete(f"/api/sessions/{created['id']}")
        assert response.status_code == 200
        assert client.get(f"/api/sessions/{created['id']}").status_code == 404

    def test_list_sessions_by_facilitator(self, client):
        fac = client.post("/api/facilitators", json={"name": "ListTest"}).json()
        client.post("/api/sessions", json={"facilitator_id": fac["id"], "title": "S1"}).json()
        client.post("/api/sessions", json={"facilitator_id": fac["id"], "title": "S2"}).json()
        response = client.get(f"/api/facilitators/{fac['id']}/sessions")
        assert response.status_code == 200
        assert len(response.json()) == 2


class TestPracticesAPI:
    def test_add_practice(self, client):
        fac = client.post("/api/facilitators", json={"name": "PratiquesTest"}).json()
        sess = client.post("/api/sessions", json={
            "facilitator_id": fac["id"], "title": "Avec Pratiques",
        }).json()
        response = client.post(f"/api/sessions/{sess['id']}/practices", json={
            "practice_id": "1", "titre": "Brainstorming",
            "duration_minutes": 30, "source": "rag",
        })
        assert response.status_code == 201
        assert response.json()["titre"] == "Brainstorming"

    def test_list_practices(self, client):
        fac = client.post("/api/facilitators", json={"name": "ListPratiques"}).json()
        sess = client.post("/api/sessions", json={
            "facilitator_id": fac["id"], "title": "Liste Pratiques",
        }).json()
        client.post(f"/api/sessions/{sess['id']}/practices", json={
            "practice_id": "1", "titre": "Pratique A",
            "duration_minutes": 20, "source": "rag",
        })
        response = client.get(f"/api/sessions/{sess['id']}/practices")
        assert response.status_code == 200
        assert len(response.json()) >= 1

    def test_remove_practice(self, client):
        fac = client.post("/api/facilitators", json={"name": "DelPratiques"}).json()
        sess = client.post("/api/sessions", json={
            "facilitator_id": fac["id"], "title": "Sup Pratiques",
        }).json()
        p = client.post(f"/api/sessions/{sess['id']}/practices", json={
            "practice_id": "2", "titre": "À supprimer",
            "duration_minutes": 15, "source": "rag",
        }).json()
        response = client.delete(f"/api/sessions/{sess['id']}/practices/{p['id']}")
        assert response.status_code == 200

    def test_search_practices_endpoint(self, client):
        with patch("Agent.Main.routes.practices.search_practices",
                   return_value=[{"practice_id": "1", "titre": "Matrice DIXIT",
                                  "score": 0.9, "categorie": "Briser la glace"}]):
            response = client.get("/api/practices/search?q=icebreaker")
            assert response.status_code == 200
            assert len(response.json()) > 0

    def test_special_practices(self, client):
        response = client.get("/api/practices/special")
        assert response.status_code == 200
        specials = response.json()
        assert len(specials) >= 4
        titles = [s["titre"] for s in specials]
        assert "Accueil" in titles


class TestParticipantsAPI:
    def test_create_participant_through_session(self, client):
        fac = client.post("/api/facilitators", json={"name": "PartTest"}).json()
        sess = client.post("/api/sessions", json={
            "facilitator_id": fac["id"], "title": "Participants",
        }).json()
        response = client.post(f"/api/sessions/{sess['id']}/participants", json={
            "first_name": "Alice", "last_name": "Martin",
            "email": "alice@test.com", "role": "Dev",
        })
        assert response.status_code == 201
        assert response.json()["first_name"] == "Alice"

    def test_add_existing_participant_to_session(self, client):
        fac = client.post("/api/facilitators", json={"name": "AddPart"}).json()
        sess = client.post("/api/sessions", json={
            "facilitator_id": fac["id"], "title": "Add Part",
        }).json()
        p = client.post(f"/api/sessions/{sess['id']}/participants", json={
            "first_name": "Bob", "last_name": "Dupont",
        }).json()
        # Create another session and add the same participant
        sess2 = client.post("/api/sessions", json={
            "facilitator_id": fac["id"], "title": "Second",
        }).json()
        response = client.post(f"/api/sessions/{sess2['id']}/participants", json={
            "participant_id": p["id"],
        })
        assert response.status_code == 201
        assert response.json()["first_name"] == "Bob"

    def test_list_session_participants(self, client):
        fac = client.post("/api/facilitators", json={"name": "ListPart"}).json()
        sess = client.post("/api/sessions", json={
            "facilitator_id": fac["id"], "title": "List Part",
        }).json()
        client.post(f"/api/sessions/{sess['id']}/participants", json={
            "first_name": "Eve", "last_name": "Test",
        }).json()
        response = client.get(f"/api/sessions/{sess['id']}/participants")
        assert response.status_code == 200
        assert len(response.json()) >= 1


class TestClientsTeamsAPI:
    def test_create_client(self, client):
        response = client.post("/api/clients", json={"name": "Acme Corp"})
        assert response.status_code == 201
        assert response.json()["name"] == "Acme Corp"

    def test_create_team(self, client):
        response = client.post("/api/teams", json={"name": "Équipe Alpha"})
        assert response.status_code == 201
        assert response.json()["name"] == "Équipe Alpha"

    def test_add_team_to_session(self, client):
        fac = client.post("/api/facilitators", json={"name": "TeamTest"}).json()
        sess = client.post("/api/sessions", json={
            "facilitator_id": fac["id"], "title": "Avec Équipe",
        }).json()
        team = client.post("/api/teams", json={"name": "Team Session"}).json()
        response = client.post(f"/api/sessions/{sess['id']}/teams", json={"team_id": team["id"]})
        assert response.status_code == 200


class TestConfigEndpoint:
    def test_get_llm_config(self, client):
        response = client.get("/api/config/llm")
        assert response.status_code == 200
        data = response.json()
        assert "mode" in data

    def test_post_llm_config(self, client):
        response = client.post("/api/config/llm", json={"mode": "openai"})
        assert response.status_code == 200


class TestAgentEndpoint:
    def test_agent_chat_simple_response(self, client):
        response = client.post("/api/agent/chat", json={
            "session_id": 0, "message": "Bonjour",
        })
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
        assert "RÉSOLU" not in data["reply"]

    def test_agent_chat_strips_markers(self, client):
        response = client.post("/api/agent/chat", json={
            "session_id": 0, "message": "Test",
        })
        data = response.json()
        assert "||RÉSOLU||" not in data["reply"]
        assert "||NON_RÉSOLU||" not in data["reply"]

    def test_agent_chat_includes_tool_results(self, client):
        response = client.post("/api/agent/chat", json={
            "session_id": 0, "message": "Cherche icebreaker",
        })
        assert response.status_code == 200
        assert "tool_results" in response.json()
