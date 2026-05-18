from .schema import get_connection


# ── Clients ──────────────────────────────────────────────────────────────────

def list_clients() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM clients ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def create_client(name: str) -> dict:
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO clients (name) VALUES (?)", (name,))
        conn.commit()
        row = conn.execute("SELECT * FROM clients WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


def get_client(client_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    return dict(row) if row else None


# ── Teams ─────────────────────────────────────────────────────────────────────

def list_teams(client_id: int = None) -> list[dict]:
    with get_connection() as conn:
        if client_id is not None:
            rows = conn.execute(
                "SELECT * FROM teams WHERE client_id = ? ORDER BY name", (client_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM teams ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def create_team(name: str, client_id: int = None) -> dict:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO teams (name, client_id) VALUES (?,?)", (name, client_id)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM teams WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


def get_team(team_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    return dict(row) if row else None


def get_team_participants(team_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT p.* FROM participants p
               JOIN team_participants tp ON tp.participant_id = p.id
               WHERE tp.team_id = ?
               ORDER BY p.last_name, p.first_name""",
            (team_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_participant_to_team(team_id: int, participant_id: int) -> bool:
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT 1 FROM team_participants WHERE team_id=? AND participant_id=?",
            (team_id, participant_id),
        ).fetchone()
        if existing:
            return False
        conn.execute(
            "INSERT INTO team_participants (team_id, participant_id) VALUES (?,?)",
            (team_id, participant_id),
        )
        conn.commit()
    return True


def remove_participant_from_team(team_id: int, participant_id: int) -> bool:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM team_participants WHERE team_id=? AND participant_id=?",
            (team_id, participant_id),
        )
        conn.commit()
    return True
