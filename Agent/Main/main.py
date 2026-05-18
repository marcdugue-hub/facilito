"""
Facilito — FastAPI server
Launch: python -m Agent.Main.main [--openai | --deepseek]
"""
import argparse
import json
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

_BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BASE_DIR))
load_dotenv(_BASE_DIR / "Agent" / ".env")

from Agent.Tools.Database.schema import init_db
from Agent.Tools.Database import facilitators as db_fac
from Agent.Tools.Database import sessions as db_ses
from Agent.Tools.Database import participants as db_par
from Agent.Tools.Database import clients_teams as db_ct
from Agent.Tools.Memory.store import build_system_prompt, get_history, add_message, add_raw_message
from Agent.Tools.RAG.search import search_practices
from Agent.Tools.Database.analytics import (
    log_event, log_rating, get_kpis, get_logs, get_cost_config, set_cost_config
)

# ── Config ────────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    with open(_BASE_DIR / "Agent" / "Config" / "app_config.yaml") as f:
        return yaml.safe_load(f)


def _load_special_practices() -> list[dict]:
    with open(_BASE_DIR / "Agent" / "Config" / "special_practices.yaml") as f:
        return yaml.safe_load(f)


# ── CLI args + LLM provider ───────────────────────────────────────────────────

def _build_provider(mode: str):
    cfg = _load_config()
    if mode == "deepseek":
        from Agent.LLM.deepseek_provider import DeepSeekProvider
        return DeepSeekProvider(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            model=cfg["llm"]["deepseek_model"],
            base_url=cfg["llm"]["deepseek_base_url"],
        )
    from Agent.LLM.openai_provider import OpenAIProvider
    return OpenAIProvider(api_key=os.environ["OPENAI_API_KEY"], model=cfg["llm"]["openai_model"])


# ── Agent tools definition ────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_facilitators",
            "description": "Liste tous les facilitateurs existants avec leur identifiant. Utiliser pour trouver l'ID d'un facilitateur par son nom.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_practices",
            "description": "Recherche des pratiques de facilitation dans le RAG selon un besoin ou contexte.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Description du besoin ou contexte de l'atelier."},
                    "n_results": {"type": "integer", "description": "Nombre de résultats souhaités (défaut 5).", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_session_context",
            "description": "Lit l'état complet de la session en cours : participants, pratiques, durée totale.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                },
                "required": ["session_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_session",
            "description": "Crée une nouvelle session pour un facilitateur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "facilitator_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "date": {"type": "string", "description": "Format ISO YYYY-MM-DD"},
                    "objective": {"type": "string"},
                },
                "required": ["facilitator_id", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_session",
            "description": "Modifie le titre, la date, l'objectif ou le statut d'une session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "date": {"type": "string"},
                    "objective": {"type": "string"},
                    "status": {"type": "string", "enum": ["draft", "confirmed", "finished"]},
                },
                "required": ["session_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_practice",
            "description": "Ajoute une pratique au déroulé de la session. Utilise practice_id du RAG ou SPECIAL_*.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                    "practice_id": {"type": "string", "description": "ID de la pratique (ex: '12') ou 'SPECIAL_PAUSE'."},
                    "titre": {"type": "string"},
                    "duration_minutes": {"type": "integer"},
                    "source": {"type": "string", "enum": ["rag", "special"], "default": "rag"},
                },
                "required": ["session_id", "practice_id", "titre", "duration_minutes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_practice",
            "description": "Retire une pratique du déroulé de la session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                    "practice_row_id": {"type": "integer", "description": "ID de la ligne session_practices."},
                },
                "required": ["session_id", "practice_row_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reorder_practice",
            "description": "Déplace une pratique vers le haut ou le bas dans le déroulé.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                    "practice_row_id": {"type": "integer"},
                    "direction": {"type": "string", "enum": ["up", "down"]},
                },
                "required": ["session_id", "practice_row_id", "direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_practice_duration",
            "description": "Modifie la durée d'une pratique dans le déroulé.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                    "practice_row_id": {"type": "integer"},
                    "duration_minutes": {"type": "integer"},
                },
                "required": ["session_id", "practice_row_id", "duration_minutes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_participant",
            "description": "Crée un nouveau participant.",
            "parameters": {
                "type": "object",
                "properties": {
                    "first_name": {"type": "string"},
                    "last_name": {"type": "string"},
                    "email": {"type": "string"},
                    "role": {"type": "string"},
                },
                "required": ["first_name", "last_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_participant_to_session",
            "description": "Ajoute un participant existant à la session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                    "participant_id": {"type": "integer"},
                },
                "required": ["session_id", "participant_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_team_to_session",
            "description": "Importe tous les membres d'une équipe dans la session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                    "team_id": {"type": "integer"},
                },
                "required": ["session_id", "team_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_client",
            "description": "Crée un nouveau client (organisation, entreprise).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nom du client."},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_team",
            "description": "Crée une nouvelle équipe, optionnellement rattachée à un client.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nom de l'équipe."},
                    "client_id": {"type": "integer", "description": "ID du client auquel rattacher l'équipe (optionnel)."},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_clients",
            "description": "Liste tous les clients existants avec leur identifiant.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_teams",
            "description": "Liste toutes les équipes existantes, optionnellement filtrées par client.",
            "parameters": {
                "type": "object",
                "properties": {
                    "client_id": {"type": "integer", "description": "Filtrer par client (optionnel)."},
                },
                "required": [],
            },
        },
    },
]


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


def _dispatch_tool(name: str, args: dict, session_id: int = 0) -> str:
    if name == "list_facilitators":
        result = db_fac.list_facilitators()
        return json.dumps(result, ensure_ascii=False)
    if name == "search_practices":
        result = search_practices(args["query"], args.get("n_results", 5))
        return json.dumps(result, ensure_ascii=False)
    if name == "get_session_context":
        result = db_ses.get_session_context(args["session_id"])
        return json.dumps(result, ensure_ascii=False, default=str)
    if name == "create_session":
        result = db_ses.create_session(
            args["facilitator_id"], args["title"],
            args.get("date"), args.get("objective"),
        )
        return json.dumps(result, ensure_ascii=False, default=str)
    if name == "update_session":
        sid = args.pop("session_id")
        result = db_ses.update_session(sid, **args)
        return json.dumps(result, ensure_ascii=False, default=str)
    if name == "add_practice":
        result = db_ses.add_practice_to_session(
            args["session_id"], args["practice_id"],
            args["titre"], args["duration_minutes"],
            args.get("source", "rag"),
        )
        return json.dumps(result, ensure_ascii=False, default=str)
    if name == "remove_practice":
        result = db_ses.remove_practice_from_session(args["session_id"], args["practice_row_id"])
        return json.dumps({"ok": result})
    if name == "reorder_practice":
        result = db_ses.reorder_practice(args["session_id"], args["practice_row_id"], args["direction"])
        return json.dumps(result, ensure_ascii=False, default=str)
    if name == "update_practice_duration":
        result = db_ses.update_practice_duration(
            args["session_id"], args["practice_row_id"], args["duration_minutes"]
        )
        return json.dumps(result, ensure_ascii=False, default=str)
    if name == "create_participant":
        result = db_par.create_participant(
            args["first_name"], args["last_name"],
            args.get("email"), args.get("role"),
        )
        return json.dumps(result, ensure_ascii=False, default=str)
    if name == "add_participant_to_session":
        result = db_par.add_participant_to_session(args["session_id"], args["participant_id"])
        return json.dumps({"ok": result})
    if name == "add_team_to_session":
        result = db_ses.add_team_to_session(args["session_id"], args["team_id"])
        return json.dumps({"added": result})
    if name == "create_client":
        result = db_ct.create_client(args["name"])
        return json.dumps(result, ensure_ascii=False)
    if name == "create_team":
        result = db_ct.create_team(args["name"], args.get("client_id"))
        return json.dumps(result, ensure_ascii=False)
    if name == "list_clients":
        result = db_ct.list_clients()
        return json.dumps(result, ensure_ascii=False)
    if name == "list_teams":
        result = db_ct.list_teams(args.get("client_id"))
        return json.dumps(result, ensure_ascii=False)
    return json.dumps({"error": f"Unknown tool: {name}"})


# ── App factory ───────────────────────────────────────────────────────────────

def create_app(llm_mode: str = "openai") -> FastAPI:
    provider = _build_provider(llm_mode)
    app = FastAPI(title="Facilito")

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    illustrations_dir = _BASE_DIR / "illustrations"
    mascotte_dir = _BASE_DIR / "Mascotte"
    app.mount("/illustrations", StaticFiles(directory=str(illustrations_dir)), name="illustrations")
    app.mount("/mascotte", StaticFiles(directory=str(mascotte_dir)), name="mascotte")

    init_db()

    # ── Request models ────────────────────────────────────────────────────────

    class FacilitatorCreate(BaseModel):
        name: str

    class SessionCreate(BaseModel):
        facilitator_id: int
        title: str
        date: str | None = None
        objective: str | None = None

    class SessionUpdate(BaseModel):
        title: str | None = None
        date: str | None = None
        objective: str | None = None
        status: str | None = None

    class PracticeAdd(BaseModel):
        practice_id: str
        titre: str
        duration_minutes: int
        source: str = "rag"

    class PracticeUpdate(BaseModel):
        duration_minutes: int | None = None
        direction: str | None = None

    class ParticipantCreate(BaseModel):
        first_name: str
        last_name: str
        email: str | None = None
        role: str | None = None

    class ParticipantAdd(BaseModel):
        participant_id: int | None = None
        first_name: str | None = None
        last_name: str | None = None
        email: str | None = None
        role: str | None = None

    class TeamAdd(BaseModel):
        team_id: int

    class ClientCreate(BaseModel):
        name: str

    class TeamCreate(BaseModel):
        name: str
        client_id: int | None = None

    class TeamParticipantAdd(BaseModel):
        participant_id: int | None = None
        first_name: str | None = None
        last_name: str | None = None
        email: str | None = None
        role: str | None = None

    class ChatMessage(BaseModel):
        session_id: int
        message: str

    # ── Routes ────────────────────────────────────────────────────────────────

    @app.get("/")
    def index():
        return FileResponse(str(static_dir / "index.html"))

    # Facilitators
    @app.get("/api/facilitators")
    def get_facilitators():
        return db_fac.list_facilitators()

    @app.post("/api/facilitators", status_code=201)
    def post_facilitator(body: FacilitatorCreate):
        return db_fac.create_facilitator(body.name)

    @app.get("/api/facilitators/{fid}")
    def get_facilitator(fid: int):
        f = db_fac.get_facilitator(fid)
        if not f:
            raise HTTPException(404)
        return f

    @app.get("/api/facilitators/{fid}/sessions")
    def get_facilitator_sessions(fid: int):
        return db_ses.list_sessions(fid)

    # Sessions
    @app.post("/api/sessions", status_code=201)
    def post_session(body: SessionCreate):
        return db_ses.create_session(body.facilitator_id, body.title, body.date, body.objective)

    @app.get("/api/sessions/{sid}")
    def get_session(sid: int):
        s = db_ses.get_session_context(sid)
        if not s:
            raise HTTPException(404)
        return s

    @app.patch("/api/sessions/{sid}")
    def patch_session(sid: int, body: SessionUpdate):
        s = db_ses.update_session(sid, **body.model_dump(exclude_none=True))
        if not s:
            raise HTTPException(404)
        return s

    @app.delete("/api/sessions/{sid}")
    def del_session(sid: int):
        db_ses.delete_session(sid)
        return {"ok": True}

    # Practices in session
    @app.get("/api/sessions/{sid}/practices")
    def get_practices(sid: int):
        return db_ses.get_session_practices(sid)

    @app.post("/api/sessions/{sid}/practices", status_code=201)
    def post_practice(sid: int, body: PracticeAdd):
        return db_ses.add_practice_to_session(sid, body.practice_id, body.titre, body.duration_minutes, body.source)

    @app.patch("/api/sessions/{sid}/practices/{pid}")
    def patch_practice(sid: int, pid: int, body: PracticeUpdate):
        if body.duration_minutes is not None:
            return db_ses.update_practice_duration(sid, pid, body.duration_minutes)
        if body.direction is not None:
            return db_ses.reorder_practice(sid, pid, body.direction)
        raise HTTPException(400, "Provide duration_minutes or direction")

    @app.delete("/api/sessions/{sid}/practices/{pid}")
    def del_practice(sid: int, pid: int):
        db_ses.remove_practice_from_session(sid, pid)
        return {"ok": True}

    # Participants in session
    @app.get("/api/sessions/{sid}/participants")
    def get_participants(sid: int):
        return db_par.get_session_participants(sid)

    @app.post("/api/sessions/{sid}/participants", status_code=201)
    def post_participant(sid: int, body: ParticipantAdd):
        if body.participant_id:
            db_par.add_participant_to_session(sid, body.participant_id)
            return db_par.get_participant(body.participant_id)
        p = db_par.create_participant(body.first_name, body.last_name, body.email, body.role)
        db_par.add_participant_to_session(sid, p["id"])
        return p

    @app.delete("/api/sessions/{sid}/participants/{pid}")
    def del_participant(sid: int, pid: int):
        db_par.remove_participant_from_session(sid, pid)
        return {"ok": True}

    @app.post("/api/sessions/{sid}/teams")
    def post_team_to_session(sid: int, body: TeamAdd):
        added = db_ses.add_team_to_session(sid, body.team_id)
        return {"added": added}

    # Clients
    @app.get("/api/clients")
    def get_clients():
        return db_ct.list_clients()

    @app.post("/api/clients", status_code=201)
    def post_client(body: ClientCreate):
        return db_ct.create_client(body.name)

    # Teams
    @app.get("/api/teams")
    def get_teams(client_id: int = None):
        return db_ct.list_teams(client_id)

    @app.post("/api/teams", status_code=201)
    def post_team(body: TeamCreate):
        return db_ct.create_team(body.name, body.client_id)

    @app.get("/api/teams/{tid}/participants")
    def get_team_participants(tid: int):
        return db_ct.get_team_participants(tid)

    @app.post("/api/teams/{tid}/participants", status_code=201)
    def post_team_participant(tid: int, body: TeamParticipantAdd):
        if body.participant_id:
            db_ct.add_participant_to_team(tid, body.participant_id)
            return db_par.get_participant(body.participant_id)
        p = db_par.create_participant(body.first_name, body.last_name, body.email, body.role)
        db_ct.add_participant_to_team(tid, p["id"])
        return p

    # Participants (global)
    @app.get("/api/participants")
    def get_all_participants():
        return db_par.list_participants()

    # Practices search + special
    @app.get("/api/practices/search")
    def search(q: str, n: int = 5):
        return search_practices(q, n)

    @app.get("/api/practices/special")
    def get_special():
        return _load_special_practices()

    # Mascots
    @app.get("/api/mascots")
    def get_mascots():
        files = [f.name for f in mascotte_dir.iterdir() if f.suffix.lower() in {".png", ".jpg", ".jpeg"}]
        return sorted(files)

    # PDF export
    @app.get("/api/sessions/{sid}/export/pdf")
    def export_pdf(sid: int):
        from weasyprint import HTML as WP_HTML
        ctx = db_ses.get_session_context(sid)
        if not ctx:
            raise HTTPException(404)
        html = _render_pdf_html(ctx)
        pdf_bytes = WP_HTML(string=html).write_pdf()
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="session-{sid}.pdf"'},
        )

    # ── Dashboard endpoints ───────────────────────────────────────────────────

    class RatingBody(BaseModel):
        session_id: int
        rating: int

    class CostConfigBody(BaseModel):
        cost_in: float
        cost_out: float

    @app.get("/api/dashboard/kpis")
    def dashboard_kpis():
        return get_kpis()

    @app.get("/api/dashboard/logs")
    def dashboard_logs(types: str = "", limit: int = 200):
        type_list = [t.strip() for t in types.split(",") if t.strip()] or None
        return get_logs(types=type_list, limit=limit)

    @app.post("/api/dashboard/rate")
    def dashboard_rate(body: RatingBody):
        log_rating(body.session_id, body.rating)
        return {"ok": True}

    @app.get("/api/dashboard/config")
    def dashboard_config():
        return get_cost_config()

    @app.post("/api/dashboard/config")
    def dashboard_config_update(body: CostConfigBody):
        set_cost_config(body.cost_in, body.cost_out)
        return get_cost_config()

    # ── Agent chat ────────────────────────────────────────────────────────────

    @app.post("/api/agent/chat")
    def agent_chat(body: ChatMessage):
        import time
        session_id = body.session_id
        user_msg = body.message
        start_time = time.time()

        ctx = db_ses.get_session_context(session_id)
        system_prompt = build_system_prompt(ctx)
        history = get_history(session_id)

        messages = [{"role": "system", "content": system_prompt}] + history + [
            {"role": "user", "content": user_msg}
        ]

        tool_results = []
        max_iterations = 10
        for _ in range(max_iterations):
            llm_start = time.time()
            response, usage = provider.chat(messages, TOOLS)
            llm_ms = int((time.time() - llm_start) * 1000)

            t_in  = usage.get("prompt_tokens", 0)
            t_out = usage.get("completion_tokens", 0)
            log_event(
                session_id=session_id,
                event_type="llm",
                summary=f"LLM — {t_in}T in, {t_out}T out — {llm_ms}ms",
                payload=json.dumps({
                    "messages": len(messages),
                    "tool_calls_requested": len(response.get("tool_calls") or []),
                    "response_preview": (response.get("content") or "")[:300],
                }),
                tokens_in=t_in,
                tokens_out=t_out,
                duration_ms=llm_ms,
            )

            tool_calls = response.get("tool_calls") or []
            if not tool_calls:
                raw_text = response.get("content") or ""
                # Parse resolution marker
                if "||NON_RÉSOLU||" in raw_text:
                    resolved = False
                    display_text = raw_text.replace("||NON_RÉSOLU||", "").strip()
                else:
                    resolved = True
                    display_text = raw_text.replace("||RÉSOLU||", "").strip()

                total_ms = int((time.time() - start_time) * 1000)
                log_event(
                    session_id=session_id,
                    event_type="resolution",
                    summary=f"{'✓ Résolu' if resolved else '✗ Non résolu'} — {total_ms}ms",
                    payload=json.dumps({"resolved": resolved, "reply_preview": display_text[:200]}),
                    duration_ms=total_ms,
                    resolved=resolved,
                )

                add_message(session_id, "user", user_msg)
                add_message(session_id, "assistant", display_text)
                return {"reply": display_text, "tool_results": tool_results}

            # Execute tool calls
            messages.append(response)
            # Tools that operate on the current session — always inject the correct session_id
            _SESSION_SCOPED = {
                "get_session_context", "update_session",
                "add_practice", "remove_practice", "reorder_practice", "update_practice_duration",
                "add_participant_to_session", "add_team_to_session",
            }
            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"])

                # Safety: override session_id with the verified one from the request
                if fn_name in _SESSION_SCOPED and session_id:
                    fn_args["session_id"] = session_id

                tool_start = time.time()
                try:
                    result_str = _dispatch_tool(fn_name, fn_args, session_id=session_id)
                except Exception as exc:
                    result_str = json.dumps({"error": str(exc)})

                tool_ms = int((time.time() - tool_start) * 1000)

                is_rag = fn_name == "search_practices"
                fallback = _is_rag_fallback(fn_name, result_str)
                log_event(
                    session_id=session_id,
                    event_type="rag" if is_rag else "db",
                    summary=f"{fn_name}({', '.join(f'{k}={v}' for k, v in fn_args.items())[:80]}) — {tool_ms}ms",
                    payload=result_str[:2000],
                    duration_ms=tool_ms,
                    fallback=fallback,
                )

                tool_results.append({"tool": fn_name, "args": fn_args, "result": json.loads(result_str)})
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result_str})

        total_ms = int((time.time() - start_time) * 1000)
        log_event(session_id=session_id, event_type="resolution",
                  summary=f"✗ Max itérations — {total_ms}ms",
                  payload="{}", duration_ms=total_ms, resolved=False)
        return {"reply": "Désolé, la requête a pris trop de cycles.", "tool_results": tool_results}

    return app


# ── PDF rendering ─────────────────────────────────────────────────────────────

def _render_pdf_html(ctx: dict) -> str:
    participants = ctx.get("participants", [])
    practices = ctx.get("practices", [])
    total = ctx.get("total_duration", 0)
    facilitator = ctx.get("facilitator", {})

    rows = ""
    for p in practices:
        rows += f"<tr><td>{p['titre']}</td><td>{p['duration_minutes']} min</td></tr>"

    p_list = "".join(
        f"<li>{p['first_name']} {p['last_name']}{' — ' + p['role'] if p.get('role') else ''}</li>"
        for p in participants
    )

    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<style>
  body {{ font-family: sans-serif; margin: 40px; color: #222; }}
  h1 {{ color: #2c7a4b; }} h2 {{ color: #2c7a4b; border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ padding: 8px 12px; border: 1px solid #ddd; text-align: left; }}
  th {{ background: #f0f9f4; }}
  .meta {{ color: #666; font-size: 0.9em; margin-bottom: 24px; }}
</style>
</head><body>
<h1>{ctx.get('title', 'Session')}</h1>
<p class="meta">
  Facilitateur : <strong>{facilitator.get('name', '')}</strong> &nbsp;|&nbsp;
  Date : <strong>{ctx.get('date', '') or '—'}</strong> &nbsp;|&nbsp;
  Statut : <strong>{ctx.get('status', 'draft')}</strong> &nbsp;|&nbsp;
  Durée totale : <strong>{total} min</strong>
</p>
{"<p><em>" + ctx.get("objective", "") + "</em></p>" if ctx.get("objective") else ""}
{"<h2>Participants</h2><ul>" + p_list + "</ul>" if participants else ""}
<h2>Déroulé</h2>
<table><thead><tr><th>Pratique</th><th>Durée</th></tr></thead>
<tbody>{rows}</tbody></table>
</body></html>"""


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="Facilito server")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--openai", action="store_true", default=True, help="Use OpenAI (default)")
    group.add_argument("--deepseek", action="store_true", help="Use DeepSeek")
    args = parser.parse_args()

    mode = "deepseek" if args.deepseek else "openai"
    cfg = _load_config()
    host = os.environ.get("APP_HOST", cfg["app"]["host"])
    port = int(os.environ.get("APP_PORT", cfg["app"]["port"]))
    print(f"Starting Facilito in {mode.upper()} mode on http://{host}:{port}")

    app = create_app(llm_mode=mode)
    uvicorn.run(app, host=host, port=port)
