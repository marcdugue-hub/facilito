from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> tuple[dict, dict]:
        """
        Returns (message_dict, usage_dict).
        usage_dict keys: prompt_tokens, completion_tokens, total_tokens.
        model: override the default model for this call.
        reasoning_effort: "low", "medium", or "high" (OpenAI only).
        """
        ...
