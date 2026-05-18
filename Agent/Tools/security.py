import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any

from Agent.Tools.erreur import (
    ExternalServiceError,
    InvalidAPIKeyError,
    InvalidUserInputError,
    InjectionDetectedError,
    LLMTimeoutError,
    RateLimitError,
)

try:
    # SDK v1+ / v2+
    from openai import AuthenticationError, APIError, APIConnectionError
    OpenAIError = APIError
    ServiceUnavailableError = APIConnectionError
    InvalidRequestError = type("_InvalidRequestError", (BaseException,), {})  # non utilisé v1+
except ImportError:
    try:
        # SDK v0.x (legacy)
        from openai.error import AuthenticationError, APIError, OpenAIError, ServiceUnavailableError  # type: ignore
        InvalidRequestError = APIError
        APIConnectionError = ServiceUnavailableError
    except ImportError:
        # Fallback — classes isolées pour ne PAS matcher toutes les exceptions
        AuthenticationError = type("_AuthErr", (BaseException,), {})
        APIError = type("_APIErr", (BaseException,), {})
        APIConnectionError = type("_ConnErr", (BaseException,), {})
        OpenAIError = APIError
        ServiceUnavailableError = APIConnectionError
        InvalidRequestError = APIError

_MAX_INPUT_LENGTH = int(os.environ.get("MAX_USER_INPUT_LENGTH", 5000))
_MIN_INPUT_LENGTH = int(os.environ.get("MIN_USER_INPUT_LENGTH", 1))
_LLM_TIMEOUT_SECONDS = int(os.environ.get("LLM_TIMEOUT_SECONDS", 20))
_REQUEST_RATE_LIMIT = int(os.environ.get("REQUEST_RATE_LIMIT", 10))
_REQUEST_RATE_INTERVAL = float(os.environ.get("REQUEST_RATE_INTERVAL", 1.0))

_REQUEST_HISTORY: dict[str, list[float]] = {}

_INJECTION_PATTERNS = [
    re.compile(r"\b(drop|delete|update|insert|alter|create|truncate|merge)\b.*\b(table|database|from|into|set)\b", re.I),
    re.compile(r"\b(select|union|exec|execute)\b.*\b(select|from|insert|delete|update|drop)\b", re.I),
    re.compile(r"(--|;|\bunion\b|\bOR\b|\bAND\b).*\b(select|delete|insert|update)\b", re.I),
    re.compile(r"(\bexec\b|\bxp_cmdshell\b|\bsp_executesql\b)", re.I),
    re.compile(r"(['\"]\s*or\s+1=1)", re.I),
    re.compile(r"\b(curl|wget|rm\s+-rf|nc\s+-e|bash\s+-i|powershell\b)", re.I),
]

_EMAIL_PATTERN = re.compile(r"([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_PHONE_PATTERN = re.compile(r"\b(?:\+?\d[\d .\-]{7,}\d)\b")
_IBAN_PATTERN = re.compile(r"\b[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}\b")


def detect_injection(text: str) -> list[str]:
    hits = []
    for regex in _INJECTION_PATTERNS:
        for match in regex.finditer(text):
            hits.append(match.group(0).strip())
    return hits


def validate_user_input(text: str, max_length: int | None = None) -> str:
    if not isinstance(text, str):
        raise InvalidUserInputError("Question invalide")

    cleaned = text.strip()
    if len(cleaned) < _MIN_INPUT_LENGTH:
        raise InvalidUserInputError("Question vide")

    if max_length is None:
        max_length = _MAX_INPUT_LENGTH

    if len(cleaned) > max_length:
        raise InvalidUserInputError(
            f"Question trop longue ({len(cleaned)} caractères). Limite: {max_length} caractères."
        )

    if re.search(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", cleaned):
        raise InvalidUserInputError("Caractères non autorisés détectés dans la question.")

    injection_hits = detect_injection(cleaned)
    if injection_hits:
        raise InjectionDetectedError(
            "Entrée suspecte détectée. Veuillez reformuler votre question."
        )

    return cleaned


def validate_request_rate(session_id: int | str | None) -> None:
    key = str(session_id or "anonymous")
    now = time.time()
    history = _REQUEST_HISTORY.setdefault(key, [])
    history[:] = [timestamp for timestamp in history if now - timestamp <= _REQUEST_RATE_INTERVAL]

    if len(history) >= _REQUEST_RATE_LIMIT:
        raise RateLimitError(
            "Trop de requêtes rapides. Veuillez patienter avant de reformuler votre question."
        )

    history.append(now)


def _mask_string(value: str) -> str:
    value = _EMAIL_PATTERN.sub(r"***@", value)
    value = _PHONE_PATTERN.sub("***", value)
    value = _IBAN_PATTERN.sub("***", value)
    return value


def filter_sensitive_data(payload: Any) -> Any:
    if isinstance(payload, str):
        return _mask_string(payload)
    if isinstance(payload, list):
        return [filter_sensitive_data(item) for item in payload]
    if isinstance(payload, dict):
        return {key: filter_sensitive_data(value) for key, value in payload.items()}
    return payload


def _normalize_llm_exception(exc: Exception) -> Exception:
    message = str(exc)
    lowered = message.lower()

    if isinstance(exc, FutureTimeout) or "timeout" in lowered:
        return LLMTimeoutError("Le service LLM n'a pas répondu à temps.")

    # 401 — clé invalide ou expirée (AuthenticationError uniquement, pas APIError générique)
    if isinstance(exc, AuthenticationError) or "invalid api key" in lowered or "incorrect api key" in lowered:
        return InvalidAPIKeyError("Clé API invalide ou expirée.")

    # 429 — quota dépassé ou rate limit
    if "insufficient_quota" in lowered or "quota" in lowered or "rate_limit" in lowered or "rate limit" in lowered:
        return ExternalServiceError("Quota OpenAI dépassé. Ajoutez des crédits sur platform.openai.com.")

    # Erreurs réseau / service
    if isinstance(exc, (APIError, ServiceUnavailableError, OpenAIError)) or "connection" in lowered or "failed to connect" in lowered:
        return ExternalServiceError(f"Erreur du service LLM : {message[:200]}")

    return ExternalServiceError(f"Erreur inattendue : {message[:200]}")


def _call_llm(provider: Any, messages: list[dict], tools: list[dict] | None, timeout: int) -> tuple[dict, dict]:
    def _invoke():
        return provider.chat(messages, tools)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_invoke)
        try:
            return future.result(timeout=timeout)
        except FutureTimeout as exc:
            future.cancel()
            raise LLMTimeoutError("Le service LLM n'a pas répondu dans le délai imparti.") from exc
        except Exception as exc:
            raise _normalize_llm_exception(exc) from exc


def call_llm_with_retry(
    provider: Any,
    messages: list[dict],
    tools: list[dict] | None = None,
    timeout: int | None = None,
    max_retries: int = 3,
    backoff_base: float = 0.5,
) -> tuple[dict, dict]:
    if timeout is None:
        timeout = _LLM_TIMEOUT_SECONDS

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return _call_llm(provider, messages, tools, timeout)
        except (LLMTimeoutError, InvalidAPIKeyError, ExternalServiceError) as exc:
            last_exc = exc
            if isinstance(exc, InvalidAPIKeyError):
                raise exc
            if attempt == max_retries - 1:
                raise exc

            sleep_seconds = backoff_base * (2 ** attempt)
            time.sleep(sleep_seconds)

    raise last_exc if last_exc is not None else ExternalServiceError("Erreur inconnue lors de l'appel au LLM.")
