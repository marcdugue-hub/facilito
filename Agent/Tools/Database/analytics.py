from .schema import get_connection


# ── Event logging ─────────────────────────────────────────────────────────────

def log_event(
    session_id: int,
    event_type: str,
    summary: str = "",
    payload: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    duration_ms: int = 0,
    resolved: bool | None = None,
    fallback: bool = False,
) -> None:
    resolved_val = None if resolved is None else int(resolved)
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO agent_events
               (session_id, event_type, summary, payload, tokens_in, tokens_out, duration_ms, resolved, fallback)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (session_id, event_type, summary, payload,
             tokens_in, tokens_out, duration_ms, resolved_val, int(fallback)),
        )
        conn.commit()


def log_rating(session_id: int, rating: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO agent_ratings (session_id, rating) VALUES (?,?)",
            (session_id, rating),
        )
        conn.commit()


# ── Cost config ───────────────────────────────────────────────────────────────

def get_cost_config() -> dict:
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM cost_config").fetchall()
    cfg = {r["key"]: r["value"] for r in rows}
    cfg.setdefault("cost_in",  1.5)
    cfg.setdefault("cost_out", 2.5)
    return cfg


def set_cost_config(cost_in: float, cost_out: float) -> None:
    with get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO cost_config (key, value) VALUES ('cost_in',  ?)", (cost_in,))
        conn.execute("INSERT OR REPLACE INTO cost_config (key, value) VALUES ('cost_out', ?)", (cost_out,))
        conn.commit()


# ── App settings ──────────────────────────────────────────────────────────────

def get_app_setting(key: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_app_setting(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()


# ── KPIs ──────────────────────────────────────────────────────────────────────

def get_kpis() -> dict:
    with get_connection() as conn:
        # Taux résolution auto
        total_res = conn.execute(
            "SELECT COUNT(*) FROM agent_events WHERE event_type='resolution'"
        ).fetchone()[0]
        resolved_count = conn.execute(
            "SELECT COUNT(*) FROM agent_events WHERE event_type='resolution' AND resolved=1"
        ).fetchone()[0]

        # Temps moyen traitement (ms → s)
        avg_ms = conn.execute(
            "SELECT AVG(duration_ms) FROM agent_events WHERE event_type='resolution'"
        ).fetchone()[0]

        # Satisfaction
        avg_rating = conn.execute("SELECT AVG(rating) FROM agent_ratings").fetchone()[0]
        rating_count = conn.execute("SELECT COUNT(*) FROM agent_ratings").fetchone()[0]

        # Coût
        avg_in  = conn.execute("SELECT AVG(tokens_in)  FROM agent_events WHERE event_type='llm'").fetchone()[0] or 0
        avg_out = conn.execute("SELECT AVG(tokens_out) FROM agent_events WHERE event_type='llm'").fetchone()[0] or 0
        llm_count = conn.execute("SELECT COUNT(*) FROM agent_events WHERE event_type='llm'").fetchone()[0]

        # Fallback RAG
        rag_total = conn.execute(
            "SELECT COUNT(*) FROM agent_events WHERE event_type='rag'"
        ).fetchone()[0]
        rag_fallback = conn.execute(
            "SELECT COUNT(*) FROM agent_events WHERE event_type='rag' AND fallback=1"
        ).fetchone()[0]

    cfg = get_cost_config()
    avg_cost = (avg_in * cfg["cost_in"] + avg_out * cfg["cost_out"]) / 1_000_000

    return {
        "auto_resolution":   round(resolved_count / total_res * 100, 1) if total_res else None,
        "avg_response_time": round(avg_ms / 1000, 2) if avg_ms else None,
        "avg_satisfaction":  round(avg_rating, 1) if avg_rating else None,
        "avg_cost":          round(avg_cost, 5),
        "fallback_rate":     round(rag_fallback / rag_total * 100, 1) if rag_total else None,
        "total_transactions": total_res,
        "total_ratings":      rating_count,
        "llm_calls":          llm_count,
        "rag_queries":        rag_total,
    }


# ── Logs ──────────────────────────────────────────────────────────────────────

def get_logs(types: list[str] | None = None, limit: int = 200) -> list[dict]:
    where = ""
    params = []
    if types:
        placeholders = ",".join("?" * len(types))
        where = f"WHERE event_type IN ({placeholders})"
        params = types
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM agent_events {where} ORDER BY id DESC LIMIT ?",
            params + [limit],
        ).fetchall()
    return [dict(r) for r in rows]
