from openai import OpenAI
from .base import LLMProvider


class DeepSeekProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "deepseek-chat", base_url: str = "https://api.deepseek.com"):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def chat(self, messages: list[dict], tools: list[dict] = None) -> tuple[dict, dict]:
        kwargs = {"model": self._model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        response = self._client.chat.completions.create(**kwargs)
        usage = response.usage.model_dump() if response.usage else {}
        return response.choices[0].message.model_dump(), usage
