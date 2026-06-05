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
from Agent.Tools.Memory.store import build_system_prompt, get_history, add_message, add_raw_message, clear_all_history
from Agent.Tools.RAG.search import search_practices
from Agent.Tools.Database.analytics import (
    log_event, log_rating, get_kpis, get_logs, get_cost_config, set_cost_config,
    get_app_setting, set_app_setting,
)
from Agent.Tools.security import (
    call_llm_with_retry,
    filter_sensitive_data,
    validate_request_rate,
    validate_user_input,
)
from Agent.Tools.langfuse_handler import (
    get_langfuse, is_enabled, create_trace, create_llm_generation, flush,
)
from Agent.Tools.erreur import (
    ExternalServiceError,
    InvalidAPIKeyError,
    InvalidUserInputError,
    InjectionDetectedError,
    LLMTimeoutError,
    RateLimitError,
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
        key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not key:
            raise ValueError("Clé DEEPSEEK_API_KEY absente de la configuration.")
        from Agent.LLM.deepseek_provider import DeepSeekProvider
        return DeepSeekProvider(
            api_key=key,
            model=cfg["llm"]["deepseek_model"],
            base_url=cfg["llm"]["deepseek_base_url"],
        )
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("Clé OPENAI_API_KEY absente de la configuration.")
    from Agent.LLM.openai_provider import OpenAIProvider
    return OpenAIProvider(api_key=key, model=cfg["llm"]["openai_model"])


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
            "name": "list_sessions",
            "description": "Liste toutes les sessions avec leur date, statut et facilitateur. Utilise CET outil quand l'utilisateur demande de lister des sessions, consulter un calendrier, voir les sessions à venir, ou filtrer par date/période. Les résultats contiennent les dates — tu peux ensuite les filtrer toi-même par période.",
            "parameters": {
                "type": "object",
                "properties": {
                    "facilitator_id": {"type": "integer", "description": "Filtrer par ID du facilitateur (optionnel)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_practices",
            "description": "RECHERCHE OBLIGATOIRE dans la base RAG pour trouver des pratiques de facilitation. À appeler AVANT add_practice pour voir les pratiques disponibles. Fournir un query décrivant le type de pratique recherché (ex: 'icebreaker', 'idéation', 'rétrospective').",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Mots-clés ou description du type de pratique recherché (ex: 'icebreaker', 'brainstorming', 'rétro', 'énergizer')."},
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
                    "start_time": {"type": "string", "description": "Heure de début au format HH:MM (ex: 14:00)"},
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
            "description": "Ajoute une pratique au déroulé de la session. Utilise practice_id retourné par search_practices (RAG) ou SPECIAL_*. Ne pas inventer de titre — utiliser le titre exact retourné par search_practices.",
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


def _dispatch_tool(name: str, args: dict, session_id: int = 0, embedding_mode: str = "local") -> str:
    if name == "list_facilitators":
        result = db_fac.list_facilitators()
        return json.dumps(result, ensure_ascii=False)
    if name == "list_sessions":
        result = db_ses.list_sessions(args.get("facilitator_id"))
        return json.dumps(result, ensure_ascii=False, default=str)
    if name == "search_practices":
        result = search_practices(args["query"], args.get("n_results", 5), embedding_mode=embedding_mode)
        return json.dumps(result, ensure_ascii=False)
    if name == "get_session_context":
        result = db_ses.get_session_context(args["session_id"])
        return json.dumps(result, ensure_ascii=False, default=str)
    if name == "create_session":
        result = db_ses.create_session(
            facilitator_id=args["facilitator_id"],
            title=args["title"],
            date=args.get("date"),
            start_time=args.get("start_time"),
            objective=args.get("objective"),
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
    _state = {"provider": _build_provider(llm_mode), "llm_mode": llm_mode}
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
        start_time: str | None = None
        objective: str | None = None

    class SessionUpdate(BaseModel):
        title: str | None = None
        date: str | None = None
        start_time: str | None = None
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

    class ParticipantUpdate(BaseModel):
        first_name: str | None = None
        last_name: str | None = None
        email: str | None = None
        role: str | None = None

    class ChatMessage(BaseModel):
        session_id: int
        message: str

    class LLMConfig(BaseModel):
        mode: str

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

    @app.delete("/api/facilitators/{fid}", status_code=204)
    def delete_facilitator_route(fid: int):
        if not db_fac.delete_facilitator(fid):
            raise HTTPException(404)

    @app.get("/api/facilitators/{fid}/sessions")
    def get_facilitator_sessions(fid: int):
        return db_ses.list_sessions(fid)

    # Sessions
    @app.post("/api/sessions", status_code=201)
    def post_session(body: SessionCreate):
        return db_ses.create_session(body.facilitator_id, body.title, body.date, body.start_time, body.objective)

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

    @app.get("/api/teams/{tid}/orphan-participants")
    def get_team_orphan_participants(tid: int):
        return db_ct.get_team_participants_not_in_sessions(tid)

    @app.post("/api/teams/{tid}/participants", status_code=201)
    def post_team_participant(tid: int, body: TeamParticipantAdd):
        if body.participant_id:
            db_ct.add_participant_to_team(tid, body.participant_id)
            return db_par.get_participant(body.participant_id)
        p = db_par.create_participant(body.first_name, body.last_name, body.email, body.role)
        db_ct.add_participant_to_team(tid, p["id"])
        return p

    @app.delete("/api/teams/{tid}")
    def delete_team_route(tid: int, delete_orphan_participants: bool = False):
        if delete_orphan_participants:
            orphans = db_ct.get_team_participants_not_in_sessions(tid)
            for p in orphans:
                db_par.delete_participant(p["id"])
        db_ct.delete_team(tid)
        return {"ok": True}

    # Participants (global)
    @app.get("/api/participants")
    def get_all_participants():
        return db_par.list_participants()

    @app.get("/api/participants/{pid}")
    def get_participant_route(pid: int):
        p = db_par.get_participant(pid)
        if not p:
            raise HTTPException(404)
        return p

    @app.patch("/api/participants/{pid}")
    def patch_participant(pid: int, body: ParticipantUpdate):
        p = db_par.update_participant(pid, **body.model_dump())
        if not p:
            raise HTTPException(404)
        return p

    @app.delete("/api/participants/{pid}")
    def delete_participant_route(pid: int):
        db_par.delete_participant(pid)
        return {"ok": True}

    # Practices search + special
    @app.get("/api/practices/search")
    def search(q: str, n: int = 5):
        em = "openai" if _state["llm_mode"] == "openai" else "local"
        return search_practices(q, n, embedding_mode=em)

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

    # ── LLM config ───────────────────────────────────────────────────────────

    @app.get("/api/config/llm")
    def get_llm_config():
        return {"mode": _state["llm_mode"]}

    @app.post("/api/config/llm")
    def set_llm_config(body: LLMConfig):
        mode = body.mode
        if mode not in ("openai", "deepseek"):
            raise HTTPException(400, "Mode invalide. Choisir 'openai' ou 'deepseek'.")
        try:
            _state["provider"] = _build_provider(mode)
            _state["llm_mode"] = mode
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        clear_all_history()
        return {"mode": mode}

    # ── App settings ─────────────────────────────────────────────────────────

    class VoiceModeBody(BaseModel):
        enabled: bool

    @app.get("/api/settings/voice")
    def get_voice():
        val = get_app_setting("voice_mode")
        return {"enabled": val == "on"}

    @app.post("/api/settings/voice")
    def set_voice(body: VoiceModeBody):
        set_app_setting("voice_mode", "on" if body.enabled else "off")
        return {"enabled": body.enabled}

    # ── Agent chat ────────────────────────────────────────────────────────────

    @app.post("/api/agent/chat")
    def agent_chat(body: ChatMessage):
        import time
        session_id = body.session_id
        user_msg = body.message
        start_time = time.time()

        try:
            validate_request_rate(session_id)
            user_msg = validate_user_input(user_msg)
        except InvalidUserInputError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except InjectionDetectedError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except RateLimitError as exc:
            raise HTTPException(status_code=429, detail=str(exc))

        cost_cfg = get_cost_config()
        trace = create_trace(
            "agent_chat",
            session_id=str(session_id) if session_id else None,
            metadata={"llm_mode": _state["llm_mode"], "session_id": session_id},
            input=user_msg,
        )

        ctx = db_ses.get_session_context(session_id)
        system_prompt = build_system_prompt(ctx)
        history = get_history(session_id)

        messages = [{"role": "system", "content": system_prompt}] + history + [
            {"role": "user", "content": user_msg}
        ]

        tool_results = []
        max_iterations = 10
        for iteration in range(max_iterations):
            llm_start = time.time()

            # Build a readable log of the request being sent to the LLM
            request_messages = []
            for m in messages:
                role = m.get("role", "")
                content = m.get("content", "")
                tc = m.get("tool_calls")
                if role == "system":
                    request_messages.append({"role": "system", "content": content[:600] + ("…" if len(content) > 600 else "")})
                elif tc:
                    names = [t["function"]["name"] for t in tc]
                    request_messages.append({"role": "assistant", "tool_calls": names})
                else:
                    request_messages.append({"role": role, "content": content[:800]})

            # Log BEFORE the LLM call so we can detect hangs/crashes
            log_event(
                session_id=session_id,
                event_type="llm",
                summary=f"LLM → appel #{iteration+1} en cours…",
                payload=json.dumps({
                    "mode": _state["llm_mode"],
                    "status": "pending",
                    "request": request_messages,
                }, ensure_ascii=False),
                tokens_in=0,
                tokens_out=0,
                duration_ms=0,
            )

            try:
                response, usage = call_llm_with_retry(
                    _state["provider"],
                    messages,
                    TOOLS,
                    timeout=int(os.environ.get("LLM_TIMEOUT_SECONDS", 20)),
                    max_retries=3,
                )
            except LLMTimeoutError as exc:
                log_event(
                    session_id=session_id,
                    event_type="llm",
                    summary="LLM timeout",
                    payload=str(exc),
                    duration_ms=int((time.time() - llm_start) * 1000),
                )
                flush()
                raise HTTPException(status_code=504, detail="Le service LLM n'a pas répondu à temps.")
            except InvalidAPIKeyError:
                flush()
                raise HTTPException(status_code=401, detail="Clé API invalide.")
            except ExternalServiceError as exc:
                flush()
                raise HTTPException(status_code=502, detail=f"Erreur externe du LLM : {str(exc)}")

            llm_ms = int((time.time() - llm_start) * 1000)

            t_in  = usage.get("prompt_tokens", 0)
            t_out = usage.get("completion_tokens", 0)

            cost = (t_in * cost_cfg["cost_in"] + t_out * cost_cfg["cost_out"]) / 1_000_000
            create_llm_generation(
                trace, "llm_call",
                model=getattr(_state["provider"], "_model", "unknown"),
                messages=messages, response=response, usage=usage,
                duration_ms=llm_ms, cost=cost,
            )

            payload = json.dumps({
                "mode": _state["llm_mode"],
                "status": "done",
                "request": request_messages,
                "tool_calls_requested": len(response.get("tool_calls") or []),
                "response_preview": (response.get("content") or "")[:600],
            }, ensure_ascii=False)
            log_event(
                session_id=session_id,
                event_type="llm",
                summary=f"LLM — {t_in}T in, {t_out}T out — {llm_ms}ms",
                payload=payload,
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

                display_text = filter_sensitive_data(display_text)

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
                flush()
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
                    em = "openai" if _state["llm_mode"] == "openai" else "local"
                    result_str = _dispatch_tool(fn_name, fn_args, session_id=session_id, embedding_mode=em)
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

                parsed_result = json.loads(result_str)
                safe_result = filter_sensitive_data(parsed_result)
                if fn_name == "create_session" and isinstance(parsed_result, dict) and parsed_result.get("id"):
                    session_id = parsed_result["id"]

                tool_results.append({"tool": fn_name, "args": fn_args, "result": safe_result})
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result_str})

        total_ms = int((time.time() - start_time) * 1000)
        log_event(session_id=session_id, event_type="resolution",
                  summary=f"✗ Max itérations — {total_ms}ms",
                  payload="{}", duration_ms=total_ms, resolved=False)
        flush()
        return {"reply": "Désolé, la requête a pris trop de cycles.", "tool_results": tool_results}

    return app


# ── PDF rendering ─────────────────────────────────────────────────────────────

def _add_minutes(hhmm: str, mins: int) -> str:
    h, m = map(int, hhmm.split(":"))
    t = h * 60 + m + mins
    return f"{(t // 60) % 24:02d}:{t % 60:02d}"


def _render_pdf_html(ctx: dict) -> str:
    participants = ctx.get("participants", [])
    practices = ctx.get("practices", [])
    total = ctx.get("total_duration", 0)
    facilitator = ctx.get("facilitator", {})
    start_time = ctx.get("start_time")

    status_labels = {"draft": "Brouillon", "confirmed": "Confirmé", "finished": "Terminé"}
    status_label = status_labels.get(ctx.get("status", "draft"), ctx.get("status", "draft"))

    rows = ""
    cursor = start_time
    for p in practices:
        if cursor:
            slot_end = _add_minutes(cursor, p["duration_minutes"])
            time_cell = f"<td class='tc'>{cursor}</td><td class='tc'>{slot_end}</td>"
            cursor = slot_end
        else:
            time_cell = "<td class='tc'>—</td><td class='tc'>—</td>"
        src = p.get("source", "rag")
        badge_cls = "badge-sp" if src == "special" else "badge-rag"
        badge_lbl = p.get("icone_code") or ("Spécial" if src == "special" else "RAG")
        rows += (
            f"<tr><td>{p['titre']} <span class='badge {badge_cls}'>{badge_lbl}</span></td>"
            f"<td class='dur'>{p['duration_minutes']} min</td>{time_cell}</tr>\n"
        )

    def _p_role(p):
        role = p.get("role")
        return f" <span class='role'>— {role}</span>" if role else ""

    p_list = "".join(
        f"<li>{p['first_name']} {p['last_name']}{_p_role(p)}</li>\n"
        for p in participants
    )

    timing_html = ""
    if start_time:
        timing_html = (
            f"<span>Début : <strong>{start_time}</strong></span>"
            f"<span>Fin estimée : <strong>{_add_minutes(start_time, total)}</strong></span>"
        )

    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: Arial, Helvetica, sans-serif; padding: 36px 44px; color: #01031B; background: #fff; font-size: 13px; line-height: 1.55; }}
h1 {{ font-size: 22px; font-weight: 700; color: #01031B; margin-bottom: 3px; }}
.pink {{ color: #D8346E; }}
.meta-bar {{ display: flex; flex-wrap: wrap; gap: 6px 24px; font-size: 12px; color: #6b6b80; margin: 10px 0 22px; padding: 10px 16px; background: #f7f7fb; border-radius: 8px; border-left: 4px solid #D8346E; }}
.meta-bar strong {{ color: #01031B; }}
.objective {{ font-style: italic; color: #6b6b80; margin-bottom: 20px; padding: 8px 16px; border-left: 3px solid #f2aac9; font-size: 12px; }}
h2 {{ color: #D8346E; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.7px; margin: 24px 0 8px; border-bottom: 2px solid #f2aac9; padding-bottom: 5px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
th {{ background: #fdf0f5; color: #D8346E; font-weight: 700; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; padding: 8px 10px; border-bottom: 2px solid #f2aac9; text-align: left; }}
th.tc {{ text-align: center; }}
td {{ padding: 8px 10px; border-bottom: 1px solid #e2e2ee; vertical-align: middle; }}
tr:nth-child(even) td {{ background: #fafafa; }}
td.dur {{ text-align: center; color: #6b6b80; white-space: nowrap; }}
td.tc  {{ text-align: center; color: #D8346E; font-weight: 700; white-space: nowrap; }}
.badge {{ font-size: 9px; font-weight: 700; padding: 1px 5px; border-radius: 6px; vertical-align: middle; display: inline-block; margin-left: 6px; }}
.badge-rag {{ background: #fdf0f5; color: #D8346E; }}
.badge-sp  {{ background: #f0fff4; color: #2c7a4b; }}
ul {{ padding-left: 20px; margin: 0; }}
li {{ padding: 3px 0; font-size: 12px; }}
.role {{ color: #6b6b80; }}
.footer {{ margin-top: 36px; padding-top: 10px; border-top: 1px solid #e2e2ee; font-size: 10px; color: #9ca3af; text-align: right; }}
</style>
</head><body>
<h1><span class="pink">‹</span> {ctx.get('title', 'Session')} <span class="pink">›</span></h1>
<div class="meta-bar">
  <span>Facilitateur : <strong>{facilitator.get('name', '')}</strong></span>
  <span>Date : <strong>{ctx.get('date') or '—'}</strong></span>
  <span>Statut : <strong>{status_label}</strong></span>
  <span>Durée : <strong>{total} min</strong></span>
  {timing_html}
</div>
{"<p class='objective'>" + ctx.get('objective', '') + "</p>" if ctx.get('objective') else ""}
{"<h2>Participants</h2><ul>" + p_list + "</ul>" if participants else ""}
<h2>Déroulé</h2>
<table>
  <thead><tr><th>Pratique</th><th class="tc">Durée</th><th class="tc">Début</th><th class="tc">Fin</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<p class="footer">Facilito — {ctx.get('date', '')}</p>
</body></html>"""


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="Facilito server")
    parser.add_argument("--openai", action="store_true", help="Use OpenAI")
    parser.add_argument("--deepseek", action="store_true", help="Use DeepSeek (default)")
    args = parser.parse_args()

    mode = "deepseek" if args.deepseek else ("openai" if args.openai else "deepseek")
    cfg = _load_config()
    host = os.environ.get("APP_HOST", cfg["app"]["host"])
    port = int(os.environ.get("APP_PORT", cfg["app"]["port"]))
    print(f"Starting Facilito in {mode.upper()} mode on http://{host}:{port}")

    app = create_app(llm_mode=mode)
    uvicorn.run(app, host=host, port=port)
