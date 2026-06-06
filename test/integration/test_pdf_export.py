"""Tests d'intégration — Export PDF.

Vérifie que la génération de PDF via weasyprint fonctionne :
- Création d'une session avec données via l'API HTTP
- Export du PDF via l'endpoint dédié
- Validation du contenu du PDF (en-têtes, signature)

Marqueur weasyprint : ignoré si libpango n'est pas installé."""
import pytest


@pytest.mark.weasyprint
class TestPDFExport:
    def _create_data(self, client):
        fac = client.post("/api/facilitators", json={"name": "PDF Fac"}).json()
        sess = client.post("/api/sessions", json={
            "facilitator_id": fac["id"], "title": "Atelier PDF",
            "date": "2026-07-15", "start_time": "09:00",
            "objective": "Tester le PDF",
        }).json()
        client.post(f"/api/sessions/{sess['id']}/participants", json={
            "first_name": "Alice", "last_name": "Martin",
            "email": "alice@test.com", "role": "Dev",
        })
        client.post(f"/api/sessions/{sess['id']}/practices", json={
            "practice_id": "1", "titre": "Brainstorming",
            "duration_minutes": 30, "source": "rag",
        })
        client.post(f"/api/sessions/{sess['id']}/practices", json={
            "practice_id": "SPECIAL_PAUSE", "titre": "Pause",
            "duration_minutes": 10, "source": "special",
        })
        return sess["id"]

    def test_pdf_export_returns_valid_pdf(self, client):
        sid = self._create_data(client)
        response = client.get(f"/api/sessions/{sid}/export/pdf")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")

    def test_pdf_export_contains_title(self, client):
        sid = self._create_data(client)
        response = client.get(f"/api/sessions/{sid}/export/pdf")
        assert "Atelier PDF" in response.text

    def test_pdf_export_contains_participants(self, client):
        sid = self._create_data(client)
        response = client.get(f"/api/sessions/{sid}/export/pdf")
        assert "Alice" in response.text
        assert "Martin" in response.text

    def test_pdf_export_contains_practices(self, client):
        sid = self._create_data(client)
        response = client.get(f"/api/sessions/{sid}/export/pdf")
        assert "Brainstorming" in response.text
        assert "Pause" in response.text

    def test_pdf_export_meta_bar(self, client):
        sid = self._create_data(client)
        response = client.get(f"/api/sessions/{sid}/export/pdf")
        assert "Facilitateur" in response.text
        assert "09:00" in response.text

    def test_pdf_export_content_disposition(self, client):
        sid = self._create_data(client)
        response = client.get(f"/api/sessions/{sid}/export/pdf")
        assert "attachment" in response.headers["content-disposition"]
        assert f"session-{sid}.pdf" in response.headers["content-disposition"]

    def test_pdf_export_not_found(self, client):
        response = client.get("/api/sessions/99999/export/pdf")
        assert response.status_code == 404

    def test_pdf_export_empty_session(self, client):
        fac = client.post("/api/facilitators", json={"name": "Vide PDF"}).json()
        sess = client.post("/api/sessions", json={
            "facilitator_id": fac["id"], "title": "Session Vide",
            "date": "2026-08-01",
        }).json()
        response = client.get(f"/api/sessions/{sess['id']}/export/pdf")
        assert response.status_code == 200
        assert response.content.startswith(b"%PDF")
        assert "Session Vide" in response.text
