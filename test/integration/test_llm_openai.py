"""Tests d'intégration — Agent/LLM/openai_provider.py (appels API réels).

Ces tests vérifient le bon fonctionnement du provider OpenAI
avec une vraie clé API. Ignorés si la clé est invalide."""
import os
import pytest


@pytest.mark.openai
class TestOpenAIProvider:
    def test_basic_chat(self):
        from Agent.LLM.openai_provider import OpenAIProvider
        provider = OpenAIProvider(api_key=os.environ["OPENAI_API_KEY"])
        msg, usage = provider.chat([
            {"role": "user", "content": "Réponds en un seul mot français : Bonjour"}
        ])
        assert msg["role"] == "assistant"
        assert isinstance(msg.get("content"), str)
        assert len(msg["content"]) > 0
        assert usage["prompt_tokens"] > 0
        assert usage["completion_tokens"] > 0

    def test_response_contains_text(self):
        from Agent.LLM.openai_provider import OpenAIProvider
        provider = OpenAIProvider(api_key=os.environ["OPENAI_API_KEY"])
        msg, usage = provider.chat([
            {"role": "user", "content": "Dis 'TEST123' sans rien d'autre"}
        ])
        assert "TEST123" in msg.get("content", "")

    def test_chat_with_tools(self):
        from Agent.LLM.openai_provider import OpenAIProvider
        provider = OpenAIProvider(api_key=os.environ["OPENAI_API_KEY"])
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

    def test_usage_contains_tokens(self):
        from Agent.LLM.openai_provider import OpenAIProvider
        provider = OpenAIProvider(api_key=os.environ["OPENAI_API_KEY"])
        _, usage = provider.chat([
            {"role": "user", "content": "Dis 'test'"}
        ])
        assert "prompt_tokens" in usage
        assert "completion_tokens" in usage
        assert "total_tokens" in usage
        assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


@pytest.mark.openai
class TestOpenAIAgentFlow:
    def test_agent_chat_through_http(self):
        from Agent.Main.main import create_app
        from fastapi.testclient import TestClient
        app = create_app("openai")
        client = TestClient(app)

        response = client.post("/api/agent/chat", json={
            "session_id": 0,
            "message": "Réponds uniquement par 'Bonjour'",
        })
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
        assert len(data["reply"]) > 0

    def test_agent_creates_session(self):
        from Agent.Main.main import create_app
        from fastapi.testclient import TestClient
        from Agent.Tools.Database.facilitators import create_facilitator
        app = create_app("openai")
        client = TestClient(app)

        fac = create_facilitator("Test OpenAI")
        response = client.post("/api/agent/chat", json={
            "session_id": 0,
            "message": f"Crée une session 'Atelier Test' pour le facilitateur {fac['id']}",
        })
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
