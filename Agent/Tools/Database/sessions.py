from .schema import get_connection
from .clients_teams import get_team_participants
from .participants import add_participant_to_session


# ── Sessions ──────────────────────────────────────────────────────────────────

def list_sessions(facilitator_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE facilitator_id = ? ORDER BY date DESC, created_at DESC",
            (facilitator_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def create_session(facilitator_id: int, title: str, date: str = None, start_time: str = None, objective: str = None) -> dict:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (facilitator_id, title, date, start_time, objective) VALUES (?,?,?,?,?)",
            (facilitator_id, title, date, start_time, objective),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


def get_session(session_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return dict(row) if row else None


def update_session(session_id: int, **kwargs) -> dict | None:
    allowed = {"title", "date", "start_time", "objective", "status"}
    fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not fields:
        return get_session(session_id)
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [session_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE sessions SET {set_clause} WHERE id = ?", values)
        conn.commit()
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return dict(row) if row else None


def delete_session(session_id: int) -> bool:
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
    return True


def get_session_context(session_id: int) -> dict | None:
    """Returns full session context including facilitator, participants and practices."""
    from .facilitators import get_facilitator
    from .participants import get_session_participants

    session = get_session(session_id)
    if not session:
        return None
    session["facilitator"] = get_facilitator(session["facilitator_id"])
    session["participants"] = get_session_participants(session_id)
    session["practices"] = get_session_practices(session_id)
    session["total_duration"] = sum(p["duration_minutes"] for p in session["practices"])
    return session


# ── Session Practices ─────────────────────────────────────────────────────────

def get_session_practices(session_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM session_practices WHERE session_id = ? ORDER BY position",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_practice_to_session(
    session_id: int,
    practice_id: str,
    titre: str,
    duration_minutes: int,
    source: str = "rag",
) -> dict:
    with get_connection() as conn:
        max_pos = conn.execute(
            "SELECT COALESCE(MAX(position), -1) FROM session_practices WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]
        cur = conn.execute(
            """INSERT INTO session_practices
               (session_id, practice_id, source, titre, duration_minutes, position)
               VALUES (?,?,?,?,?,?)""",
            (session_id, practice_id, source, titre, duration_minutes, max_pos + 1),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM session_practices WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return dict(row)


def remove_practice_from_session(session_id: int, practice_row_id: int) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT position FROM session_practices WHERE id = ? AND session_id = ?",
            (practice_row_id, session_id),
        ).fetchone()
        if not row:
            return False
        pos = row["position"]
        conn.execute(
            "DELETE FROM session_practices WHERE id = ? AND session_id = ?",
            (practice_row_id, session_id),
        )
        conn.execute(
            "UPDATE session_practices SET position = position - 1 WHERE session_id = ? AND position > ?",
            (session_id, pos),
        )
        conn.commit()
    return True


def reorder_practice(session_id: int, practice_row_id: int, direction: str) -> list[dict]:
    """Move practice up or down. direction: 'up' | 'down'."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, position FROM session_practices WHERE id = ? AND session_id = ?",
            (practice_row_id, session_id),
        ).fetchone()
        if not row:
            return get_session_practices(session_id)
        pos = row["position"]
        swap_pos = pos - 1 if direction == "up" else pos + 1
        swap = conn.execute(
            "SELECT id FROM session_practices WHERE session_id = ? AND position = ?",
            (session_id, swap_pos),
        ).fetchone()
        if swap:
            conn.execute(
                "UPDATE session_practices SET position = ? WHERE id = ?", (swap_pos, practice_row_id)
            )
            conn.execute(
                "UPDATE session_practices SET position = ? WHERE id = ?", (pos, swap["id"])
            )
            conn.commit()
    return get_session_practices(session_id)


def update_practice_duration(session_id: int, practice_row_id: int, duration_minutes: int) -> dict | None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE session_practices SET duration_minutes = ? WHERE id = ? AND session_id = ?",
            (duration_minutes, practice_row_id, session_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM session_practices WHERE id = ?", (practice_row_id,)
        ).fetchone()
    return dict(row) if row else None


# ── Session — Team import ─────────────────────────────────────────────────────

def add_team_to_session(session_id: int, team_id: int) -> int:
    """Add all team members to session. Returns count of added participants."""
    participants = get_team_participants(team_id)
    added = 0
    for p in participants:
        if add_participant_to_session(session_id, p["id"]):
            added += 1
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT 1 FROM session_teams WHERE session_id=? AND team_id=?",
            (session_id, team_id),
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO session_teams (session_id, team_id) VALUES (?,?)",
                (session_id, team_id),
            )
            conn.commit()
    return added
