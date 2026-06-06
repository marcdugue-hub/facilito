from openai import OpenAI
from .openai_provider import OpenAIProvider


class DeepSeekProvider(OpenAIProvider):
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
