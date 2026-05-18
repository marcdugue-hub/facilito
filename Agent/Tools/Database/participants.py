from .schema import get_connection


def list_participants() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM participants ORDER BY last_name, first_name"
        ).fetchall()
    return [dict(r) for r in rows]


def create_participant(first_name: str, last_name: str, email: str = None, role: str = None) -> dict:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO participants (first_name, last_name, email, role) VALUES (?,?,?,?)",
            (first_name, last_name, email, role),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM participants WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


def get_participant(participant_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM participants WHERE id = ?", (participant_id,)).fetchone()
    return dict(row) if row else None


def get_session_participants(session_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT p.* FROM participants p
               JOIN session_participants sp ON sp.participant_id = p.id
               WHERE sp.session_id = ?
               ORDER BY p.last_name, p.first_name""",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_participant_to_session(session_id: int, participant_id: int) -> bool:
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT 1 FROM session_participants WHERE session_id=? AND participant_id=?",
            (session_id, participant_id),
        ).fetchone()
        if existing:
            return False
        conn.execute(
            "INSERT INTO session_participants (session_id, participant_id) VALUES (?,?)",
            (session_id, participant_id),
        )
        conn.commit()
    return True


def remove_participant_from_session(session_id: int, participant_id: int) -> bool:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM session_participants WHERE session_id=? AND participant_id=?",
            (session_id, participant_id),
        )
        conn.commit()
    return True


def update_participant(participant_id: int, **kwargs) -> dict | None:
    allowed = {"first_name", "last_name", "email", "role"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM participants WHERE id = ?", (participant_id,)).fetchone()
        if not row:
            return None
        if not fields:
            return dict(row)
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(
            f"UPDATE participants SET {set_clause} WHERE id = ?",
            list(fields.values()) + [participant_id],
        )
        conn.commit()
        row = conn.execute("SELECT * FROM participants WHERE id = ?", (participant_id,)).fetchone()
    return dict(row)


def delete_participant(participant_id: int) -> bool:
    with get_connection() as conn:
        conn.execute("DELETE FROM team_participants WHERE participant_id = ?", (participant_id,))
        conn.execute("DELETE FROM session_participants WHERE participant_id = ?", (participant_id,))
        conn.execute("DELETE FROM participants WHERE id = ?", (participant_id,))
        conn.commit()
    return True
