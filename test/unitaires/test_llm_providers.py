"""Tests unitaires — Agent/LLM/openai_provider.py et deepseek_provider.py"""
from unittest.mock import patch, MagicMock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_completion(content="Réponse test", tool_calls=None,
                     prompt_tokens=50, completion_tokens=20):
    """Crée un objet completion OpenAI mocké."""
    msg = MagicMock()
    msg.model_dump.return_value = {
        "role": "assistant",
        "content": content,
        "tool_calls": tool_calls,
    }
    usage = MagicMock()
    usage.model_dump.return_value = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


# ── OpenAIProvider ────────────────────────────────────────────────────────────

def test_openai_provider_returns_tuple():
    from Agent.LLM.openai_provider import OpenAIProvider
    with patch("Agent.LLM.openai_provider.OpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create.return_value = _mock_completion("Hello")
        provider = OpenAIProvider(api_key="sk-test", model="gpt-4o")
        result = provider.chat([{"role": "user", "content": "Hi"}])
        assert isinstance(result, tuple)
        assert len(result) == 2


def test_openai_provider_message_content():
    from Agent.LLM.openai_provider import OpenAIProvider
    with patch("Agent.LLM.openai_provider.OpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create.return_value = _mock_completion("Bonjour")
        provider = OpenAIProvider(api_key="sk-test")
        message, _ = provider.chat([])
        assert message["content"] == "Bonjour"
        assert message["role"] == "assistant"


def test_openai_provider_usage_returned():
    from Agent.LLM.openai_provider import OpenAIProvider
    with patch("Agent.LLM.openai_provider.OpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create.return_value = _mock_completion(
            prompt_tokens=100, completion_tokens=40
        )
        provider = OpenAIProvider(api_key="sk-test")
        _, usage = provider.chat([])
        assert usage["prompt_tokens"] == 100
        assert usage["completion_tokens"] == 40
        assert usage["total_tokens"] == 140


def test_openai_provider_passes_tools_and_tool_choice():
    from Agent.LLM.openai_provider import OpenAIProvider
    with patch("Agent.LLM.openai_provider.OpenAI") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.chat.completions.create.return_value = _mock_completion()
        provider = OpenAIProvider(api_key="sk-test")
        tools = [{"type": "function", "function": {"name": "test"}}]
        provider.chat([{"role": "user", "content": "test"}], tools=tools)
        kwargs = mock_client.chat.completions.create.call_args[1]
        assert "tools" in kwargs
        assert kwargs["tool_choice"] == "auto"


def test_openai_provider_no_tool_choice_when_no_tools():
    from Agent.LLM.openai_provider import OpenAIProvider
    with patch("Agent.LLM.openai_provider.OpenAI") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.chat.completions.create.return_value = _mock_completion()
        provider = OpenAIProvider(api_key="sk-test")
        provider.chat([])
        kwargs = mock_client.chat.completions.create.call_args[1]
        assert "tools" not in kwargs
        assert "tool_choice" not in kwargs


def test_openai_provider_uses_specified_model():
    from Agent.LLM.openai_provider import OpenAIProvider
    with patch("Agent.LLM.openai_provider.OpenAI") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.chat.completions.create.return_value = _mock_completion()
        provider = OpenAIProvider(api_key="sk-test", model="gpt-4o-mini")
        provider.chat([])
        kwargs = mock_client.chat.completions.create.call_args[1]
        assert kwargs["model"] == "gpt-4o-mini"


# ── DeepSeekProvider ──────────────────────────────────────────────────────────

def test_deepseek_provider_returns_tuple():
    from Agent.LLM.deepseek_provider import DeepSeekProvider
    with patch("Agent.LLM.deepseek_provider.OpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create.return_value = _mock_completion()
        provider = DeepSeekProvider(api_key="sk-test")
        result = provider.chat([])
        assert isinstance(result, tuple) and len(result) == 2


def test_deepseek_provider_uses_custom_base_url():
    from Agent.LLM.deepseek_provider import DeepSeekProvider
    with patch("Agent.LLM.deepseek_provider.OpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create.return_value = _mock_completion()
        DeepSeekProvider(api_key="sk-test", base_url="https://api.deepseek.com")
        init_kwargs = mock_cls.call_args[1]
        assert init_kwargs["base_url"] == "https://api.deepseek.com"


def test_deepseek_provider_uses_deepseek_model():
    from Agent.LLM.deepseek_provider import DeepSeekProvider
    with patch("Agent.LLM.deepseek_provider.OpenAI") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.chat.completions.create.return_value = _mock_completion()
        provider = DeepSeekProvider(api_key="sk-test", model="deepseek-chat")
        provider.chat([])
        kwargs = mock_client.chat.completions.create.call_args[1]
        assert kwargs["model"] == "deepseek-chat"
