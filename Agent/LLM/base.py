from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    def chat(self, messages: list[dict], tools: list[dict] = None) -> tuple[dict, dict]:
        """
        Returns (message_dict, usage_dict).
        usage_dict keys: prompt_tokens, completion_tokens, total_tokens.
        """
        ...
