from openai import OpenAI
from .base import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        router_model: str = "gpt-4o-mini",
        simple_model: str = "gpt-4o-mini",
        complex_model: str = "gpt-4o",
    ):
        self._client = OpenAI(api_key=api_key)
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
