"""Tests unitaires — Agent/Tools/Database/analytics.py"""


# ── log_event ─────────────────────────────────────────────────────────────────

def test_log_event_persists():
    from Agent.Tools.Database.analytics import log_event, get_logs
    log_event(1, "llm", "Test call", '{"k": 1}', tokens_in=100, tokens_out=50, duration_ms=500)
    logs = get_logs()
    assert len(logs) == 1
    assert logs[0]["event_type"] == "llm"
    assert logs[0]["tokens_in"] == 100
    assert logs[0]["tokens_out"] == 50
    assert logs[0]["duration_ms"] == 500


def test_log_event_fallback_flag():
    from Agent.Tools.Database.analytics import log_event, get_logs
    log_event(1, "rag", "low score", "{}", fallback=True)
    logs = get_logs()
    assert logs[0]["fallback"] == 1


def test_log_event_resolution_marker():
    from Agent.Tools.Database.analytics import log_event, get_logs
    log_event(1, "resolution", "ok", "{}", resolved=True)
    log_event(1, "resolution", "fail", "{}", resolved=False)
    logs = get_logs(types=["resolution"])
    assert len(logs) == 2


# ── log_rating ────────────────────────────────────────────────────────────────

def test_log_rating_persists():
    from Agent.Tools.Database.analytics import log_rating, get_kpis
    log_rating(1, 5)
    kpis = get_kpis()
    assert kpis["avg_satisfaction"] == 5.0


def test_log_rating_averages_correctly():
    from Agent.Tools.Database.analytics import log_rating, get_kpis
    log_rating(1, 4)
    log_rating(1, 2)
    kpis = get_kpis()
    assert kpis["avg_satisfaction"] == 3.0


# ── cost_config ───────────────────────────────────────────────────────────────

def test_get_cost_config_defaults():
    from Agent.Tools.Database.analytics import get_cost_config
    cfg = get_cost_config()
    assert cfg["cost_in"] == 1.5
    assert cfg["cost_out"] == 2.5


def test_set_cost_config_persists():
    from Agent.Tools.Database.analytics import set_cost_config, get_cost_config
    set_cost_config(2.0, 4.0)
    cfg = get_cost_config()
    assert cfg["cost_in"] == 2.0
    assert cfg["cost_out"] == 4.0


# ── get_kpis ──────────────────────────────────────────────────────────────────

def test_get_kpis_empty_db():
    from Agent.Tools.Database.analytics import get_kpis
    kpis = get_kpis()
    assert kpis["auto_resolution"] is None
    assert kpis["avg_response_time"] is None
    assert kpis["avg_satisfaction"] is None
    assert kpis["fallback_rate"] is None
    assert kpis["avg_cost"] == 0.0


def test_get_kpis_auto_resolution_rate():
    from Agent.Tools.Database.analytics import log_event, get_kpis
    log_event(1, "resolution", "ok", "{}", resolved=True)
    log_event(1, "resolution", "fail", "{}", resolved=False)
    kpis = get_kpis()
    assert kpis["auto_resolution"] == 50.0


def test_get_kpis_avg_response_time():
    from Agent.Tools.Database.analytics import log_event, get_kpis
    log_event(1, "resolution", "fast", "{}", duration_ms=1000, resolved=True)
    log_event(1, "resolution", "slow", "{}", duration_ms=3000, resolved=True)
    kpis = get_kpis()
    assert kpis["avg_response_time"] == 2.0


def test_get_kpis_fallback_rate():
    from Agent.Tools.Database.analytics import log_event, get_kpis
    log_event(1, "rag", "good", "{}", fallback=False)
    log_event(1, "rag", "bad", "{}", fallback=True)
    kpis = get_kpis()
    assert kpis["fallback_rate"] == 50.0


def test_get_kpis_avg_cost():
    from Agent.Tools.Database.analytics import log_event, get_kpis, set_cost_config
    set_cost_config(1.0, 2.0)
    log_event(1, "llm", "call", "{}", tokens_in=1_000_000, tokens_out=500_000)
    kpis = get_kpis()
    assert abs(kpis["avg_cost"] - 2.0) < 0.001  # 1*1 + 0.5*2 = 2.0$


# ── get_logs ──────────────────────────────────────────────────────────────────

def test_get_logs_empty():
    from Agent.Tools.Database.analytics import get_logs
    assert get_logs() == []


def test_get_logs_filter_by_type():
    from Agent.Tools.Database.analytics import log_event, get_logs
    log_event(1, "llm", "LLM", "{}")
    log_event(1, "rag", "RAG", "{}")
    log_event(1, "db", "DB", "{}")
    assert len(get_logs(types=["llm"])) == 1
    assert len(get_logs(types=["llm", "rag"])) == 2
    assert len(get_logs()) == 3


def test_get_logs_respects_limit():
    from Agent.Tools.Database.analytics import log_event, get_logs
    for i in range(10):
        log_event(1, "llm", f"call {i}", "{}")
    assert len(get_logs(limit=3)) == 3


def test_get_logs_ordered_by_desc_id():
    from Agent.Tools.Database.analytics import log_event, get_logs
    log_event(1, "llm", "first", "{}")
    log_event(1, "llm", "second", "{}")
    logs = get_logs()
    assert logs[0]["summary"] == "second"
