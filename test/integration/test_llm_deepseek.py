"""Tests d'intégration — Agent/LLM/deepseek_provider.py (appels API réels).

Ces tests vérifient le bon fonctionnement du provider DeepSeek
avec une vraie clé API. Ignorés si la clé est invalide."""
import os
import pytest


@pytest.mark.deepseek
class TestDeepSeekProvider:
    def test_basic_chat(self):
        from Agent.LLM.deepseek_provider import DeepSeekProvider
        provider = DeepSeekProvider(api_key=os.environ["DEEPSEEK_API_KEY"])
        msg, usage = provider.chat([
            {"role": "user", "content": "Réponds en un seul mot : Bonjour"}
        ])
        assert msg["role"] == "assistant"
        assert "Bonjour" in msg.get("content", "")
        assert usage["prompt_tokens"] > 0
        assert usage["completion_tokens"] > 0

    def test_chat_with_tools(self):
        from Agent.LLM.deepseek_provider import DeepSeekProvider
        provider = DeepSeekProvider(api_key=os.environ["DEEPSEEK_API_KEY"])
        tools = [{
            "type": "function",
            "function": {
                "name": "test_tool",
                "description": "Un outil de test",
                "parameters": {
                    "type": "object",
                    "properties": {"input": {"type": "string"}},
                    "required": ["input"],
                },
            },
        }]
        msg, usage = provider.chat(
            [{"role": "user", "content": "Appelle test_tool avec 'hello'"}],
            tools=tools,
        )
        assert msg["role"] == "assistant"

    def test_uses_custom_base_url(self):
        from Agent.LLM.deepseek_provider import DeepSeekProvider
        provider = DeepSeekProvider(api_key=os.environ["DEEPSEEK_API_KEY"],
                                    base_url="https://api.deepseek.com")
        msg, usage = provider.chat([
            {"role": "user", "content": "Réponds en un seul mot : Salut"}
        ])
        assert "Salut" in msg.get("content", "")

    def test_usage_contains_tokens(self):
        from Agent.LLM.deepseek_provider import DeepSeekProvider
        provider = DeepSeekProvider(api_key=os.environ["DEEPSEEK_API_KEY"])
        _, usage = provider.chat([
            {"role": "user", "content": "Dis 'test'"}
        ])
        assert "prompt_tokens" in usage
        assert "completion_tokens" in usage
        assert "total_tokens" in usage


@pytest.mark.deepseek
class TestDeepSeekAgentFlow:
    def test_agent_chat_through_http(self):
        from Agent.Main.main import create_app
        from fastapi.testclient import TestClient
        app = create_app("deepseek")
        client = TestClient(app)

        response = client.post("/api/agent/chat", json={
            "session_id": 0,
            "message": "Réponds uniquement par 'Bonjour'",
        })
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
        assert "Bonjour" in data["reply"]

    def test_agent_creates_session(self):
        from Agent.Main.main import create_app
        from fastapi.testclient import TestClient
        from Agent.Tools.Database.facilitators import create_facilitator
        app = create_app("deepseek")
        client = TestClient(app)

        fac = create_facilitator("Test DeepSeek")
        response = client.post("/api/agent/chat", json={
            "session_id": 0,
            "message": f"Crée une session 'Atelier DeepSeek' pour le facilitateur {fac['id']}",
        })
        assert response.status_code == 200
        data = response.json()
        tool_names = [t["tool"] for t in data.get("tool_results", [])]
        assert "create_session" in tool_names or "Créée" in data.get("reply", "")
