"""Tool dispatch: maps tool names to handler functions (dispatch table pattern)."""

import json

from Agent.Tools.Database import facilitators as db_fac
from Agent.Tools.Database import sessions as db_ses
from Agent.Tools.Database import participants as db_par
from Agent.Tools.Database import clients_teams as db_ct
from Agent.Tools.Database.analytics import get_app_setting
from Agent.Tools.RAG.search import search_practices


DISPATCH_TABLE: dict[str, callable] = {}


def _safe_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _is_feature_enabled(key: str) -> bool:
    try:
        return get_app_setting(key) == "on"
    except Exception:
        return False


def _is_rag_fallback(fn_name: str, result_str: str) -> bool:
    if fn_name != "search_practices":
        return False
    try:
        results = json.loads(result_str)
        if not results:
            return True
        return max(r.get("score", 0) for r in results) < 0.3
    except Exception:
        return False


# ── Handlers ───────────────────────────────────────────────────────────────────

def handle_list_facilitators(args: dict, **kwargs) -> str:
    return _safe_json(db_fac.list_facilitators())


def handle_list_sessions(args: dict, **kwargs) -> str:
    return _safe_json(db_ses.list_sessions(args.get("facilitator_id")))


def handle_search_practices(args: dict, session_id: int = 0, embedding_mode: str = "local", llm_mode: str = "openai") -> str:
    do_rewrite = _is_feature_enabled("query_rewriting")
    do_hyde = _is_feature_enabled("hyde")
    do_rerank = _is_feature_enabled("rerank")
    result = search_practices(
        args["query"], args.get("n_results", 5),
        embedding_mode=embedding_mode, rewrite=do_rewrite, hyde=do_hyde,
        rerank=do_rerank, rerank_mode=llm_mode,
    )
    return _safe_json(result)


def handle_get_session_context(args: dict, **kwargs) -> str:
    return _safe_json(db_ses.get_session_context(args["session_id"]))


def handle_create_session(args: dict, **kwargs) -> str:
    result = db_ses.create_session(
        facilitator_id=args["facilitator_id"],
        title=args["title"],
        date=args.get("date"),
        start_time=args.get("start_time"),
        objective=args.get("objective"),
    )
    return _safe_json(result)


def handle_update_session(args: dict, **kwargs) -> str:
    sid = args.pop("session_id")
    result = db_ses.update_session(sid, **args)
    return _safe_json(result)


def handle_add_practice(args: dict, **kwargs) -> str:
    result = db_ses.add_practice_to_session(
        args["session_id"], args["practice_id"],
        args["titre"], args["duration_minutes"],
        args.get("source", "rag"),
    )
    return _safe_json(result)


def handle_remove_practice(args: dict, **kwargs) -> str:
    result = db_ses.remove_practice_from_session(args["session_id"], args["practice_row_id"])
    return _safe_json({"ok": result})


def handle_reorder_practice(args: dict, **kwargs) -> str:
    result = db_ses.reorder_practice(args["session_id"], args["practice_row_id"], args["direction"])
    return _safe_json(result)


def handle_update_practice_duration(args: dict, **kwargs) -> str:
    result = db_ses.update_practice_duration(
        args["session_id"], args["practice_row_id"], args["duration_minutes"]
    )
    return _safe_json(result)


def handle_create_participant(args: dict, **kwargs) -> str:
    result = db_par.create_participant(
        args["first_name"], args["last_name"],
        args.get("email"), args.get("role"),
    )
    return _safe_json(result)


def handle_add_participant_to_session(args: dict, **kwargs) -> str:
    result = db_par.add_participant_to_session(args["session_id"], args["participant_id"])
    return _safe_json({"ok": result})


def handle_add_team_to_session(args: dict, **kwargs) -> str:
    result = db_ses.add_team_to_session(args["session_id"], args["team_id"])
    return _safe_json({"added": result})


def handle_create_client(args: dict, **kwargs) -> str:
    result = db_ct.create_client(args["name"])
    return _safe_json(result)


def handle_create_team(args: dict, **kwargs) -> str:
    result = db_ct.create_team(args["name"], args.get("client_id"))
    return _safe_json(result)


def handle_list_clients(args: dict, **kwargs) -> str:
    result = db_ct.list_clients()
    return _safe_json(result)


def handle_list_teams(args: dict, **kwargs) -> str:
    result = db_ct.list_teams(args.get("client_id"))
    return _safe_json(result)


# ── Build dispatch table ───────────────────────────────────────────────────────

DISPATCH_TABLE["list_facilitators"] = handle_list_facilitators
DISPATCH_TABLE["list_sessions"] = handle_list_sessions
DISPATCH_TABLE["search_practices"] = handle_search_practices
DISPATCH_TABLE["get_session_context"] = handle_get_session_context
DISPATCH_TABLE["create_session"] = handle_create_session
DISPATCH_TABLE["update_session"] = handle_update_session
DISPATCH_TABLE["add_practice"] = handle_add_practice
DISPATCH_TABLE["remove_practice"] = handle_remove_practice
DISPATCH_TABLE["reorder_practice"] = handle_reorder_practice
DISPATCH_TABLE["update_practice_duration"] = handle_update_practice_duration
DISPATCH_TABLE["create_participant"] = handle_create_participant
DISPATCH_TABLE["add_participant_to_session"] = handle_add_participant_to_session
DISPATCH_TABLE["add_team_to_session"] = handle_add_team_to_session
DISPATCH_TABLE["create_client"] = handle_create_client
DISPATCH_TABLE["create_team"] = handle_create_team
DISPATCH_TABLE["list_clients"] = handle_list_clients
DISPATCH_TABLE["list_teams"] = handle_list_teams


# ── Public API ─────────────────────────────────────────────────────────────────

def dispatch_tool(name: str, args: dict, session_id: int = 0, embedding_mode: str = "local", llm_mode: str = "openai") -> str:
    handler = DISPATCH_TABLE.get(name)
    if handler is None:
        return _safe_json({"error": f"Unknown tool: {name}"})
    return handler(args, session_id=session_id, embedding_mode=embedding_mode, llm_mode=llm_mode)
