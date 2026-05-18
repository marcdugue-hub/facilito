from collections import defaultdict, deque
from pathlib import Path
import yaml


_BASE_DIR = Path(__file__).resolve().parents[3]


def _load_config() -> dict:
    with open(_BASE_DIR / "Agent" / "Config" / "app_config.yaml") as f:
        return yaml.safe_load(f)


_MEMORY_SIZE = _load_config()["agent"]["memory_size"]

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


def build_system_prompt(session_context: dict | None) -> str:
    lines = [
        "Tu es un assistant expert en facilitation d'ateliers collaboratifs.",
        "Tu aides les facilitateurs à concevoir des sessions efficaces en recommandant des pratiques adaptées.",
        "Tu peux agir directement sur l'application : créer des sessions, ajouter des pratiques, gérer les participants, créer des clients et des équipes.",
        "Tu ne peux PAS supprimer une session, un participant, une équipe ou un facilitateur.",
        "Réponds toujours en français.",
        "À la fin de CHAQUE réponse, ajoute sur une nouvelle ligne : '||RÉSOLU||' si tu as entièrement répondu à la demande, ou '||NON_RÉSOLU||' si tu n'as pas pu répondre.",
        "",
    ]

    if session_context:
        s = session_context
        lines += [
            "## Contexte de la session en cours",
            f"- **session_id : {s.get('id')}** (utilise TOUJOURS cet ID pour les outils)",
            f"- Titre : {s.get('title', 'Non défini')}",
            f"- Date : {s.get('date', 'Non définie')}",
            f"- Statut : {s.get('status', 'draft')}",
            f"- Objectif : {s.get('objective', 'Non défini')}",
            f"- Durée totale : {s.get('total_duration', 0)} minutes",
            "",
        ]

        participants = s.get("participants", [])
        if participants:
            lines.append(f"## Participants ({len(participants)})")
            for p in participants:
                name = f"{p['first_name']} {p['last_name']}"
                if p.get("role"):
                    name += f" ({p['role']})"
                lines.append(f"- {name}")
            lines.append("")

        practices = s.get("practices", [])
        if practices:
            lines.append(f"## Déroulé actuel ({len(practices)} pratiques)")
            for p in practices:
                lines.append(f"- [{p['id']}] {p['titre']} — {p['duration_minutes']} min ({p['source']})")
            lines.append("")

    return "\n".join(lines)
