from openai import OpenAI
from .base import LLMProvider


class DeepSeekProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        router_model: str = "deepseek-chat",
        simple_model: str = "deepseek-chat",
        complex_model: str = "deepseek-reasoner",
    ):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._router_model = router_model
        self._simple_model = simple_model
        self._complex_model = complex_model

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> tuple[dict, dict]:
        kwargs = {"model": model or self._model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
        response = self._client.chat.completions.create(**kwargs)
        usage = response.usage.model_dump() if response.usage else {}
        return response.choices[0].message.model_dump(), usage
