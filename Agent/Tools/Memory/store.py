from collections import defaultdict, deque

from Agent.Config.config import load_config


_MEMORY_SIZE = load_config()["agent"]["memory_size"]

# In-memory store: {session_id: deque of message dicts}
_histories: dict[int, deque] = defaultdict(lambda: deque(maxlen=_MEMORY_SIZE))


def get_history(session_id: int) -> list[dict]:
    return list(_histories[session_id])


def add_message(session_id: int, role: str, content: str) -> None:
    _histories[session_id].append({"role": role, "content": content})


def add_raw_message(session_id: int, message: dict) -> None:
    """Store a raw message dict (used for tool call messages)."""
    _histories[session_id].append(message)


def clear(session_id: int) -> None:
    _histories[session_id].clear()


def clear_all_history() -> None:
    _histories.clear()
