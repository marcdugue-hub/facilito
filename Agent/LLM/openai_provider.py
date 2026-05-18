from openai import OpenAI
from .base import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def chat(self, messages: list[dict], tools: list[dict] = None) -> tuple[dict, dict]:
        kwargs = {"model": self._model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        response = self._client.chat.completions.create(**kwargs)
        usage = response.usage.model_dump() if response.usage else {}
        return response.choices[0].message.model_dump(), usage
