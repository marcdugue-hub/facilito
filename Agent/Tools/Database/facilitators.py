from .schema import get_connection


def list_facilitators() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM facilitators ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def create_facilitator(name: str) -> dict:
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO facilitators (name) VALUES (?)", (name,))
        conn.commit()
        row = conn.execute("SELECT * FROM facilitators WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


def get_facilitator(facilitator_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM facilitators WHERE id = ?", (facilitator_id,)).fetchone()
    return dict(row) if row else None
