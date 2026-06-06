"""Practice REST routes (session practices + search + cards)."""

import re

import yaml
from fastapi import APIRouter, HTTPException, Request

from Agent.Tools.Database import sessions as db_ses
from Agent.Tools.RAG.search import search_practices
from Agent.Tools.markdown import md_to_html
from Agent.Tools.tool_dispatch import _is_feature_enabled
from Agent.Config.config import load_special_practices, get_project_root
from Agent.Main.models import PracticeAdd, PracticeUpdate

router = APIRouter(tags=["practices"])


@router.get("/api/sessions/{sid}/practices")
def get_practices(sid: int):
    return db_ses.get_session_practices(sid)


@router.post("/api/sessions/{sid}/practices", status_code=201)
def post_practice(sid: int, body: PracticeAdd):
    return db_ses.add_practice_to_session(sid, body.practice_id, body.titre, body.duration_minutes, body.source)


@router.patch("/api/sessions/{sid}/practices/{pid}")
def patch_practice(sid: int, pid: int, body: PracticeUpdate):
    if body.duration_minutes is not None:
        return db_ses.update_practice_duration(sid, pid, body.duration_minutes)
    if body.direction is not None:
        return db_ses.reorder_practice(sid, pid, body.direction)
    raise HTTPException(400, "Provide duration_minutes or direction")


@router.delete("/api/sessions/{sid}/practices/{pid}")
def del_practice(sid: int, pid: int):
    db_ses.remove_practice_from_session(sid, pid)
    return {"ok": True}


@router.get("/api/practices/search")
def search(request: Request, q: str, n: int = 5):
    llm_mode = request.app.state.llm_mode
    em = "openai" if llm_mode == "openai" else "local"
    do_rewrite = _is_feature_enabled("query_rewriting")
    do_hyde = _is_feature_enabled("hyde")
    do_rerank = _is_feature_enabled("rerank")
    return search_practices(q, n, embedding_mode=em, rewrite=do_rewrite, hyde=do_hyde,
                            rerank=do_rerank, rerank_mode=llm_mode)


@router.get("/api/practices/special")
def get_special():
    return load_special_practices()


@router.get("/api/practices/{practice_id}/card")
def get_practice_card(practice_id: str):
    pratiques_dir = get_project_root() / "pratiques"
    pattern = f"{practice_id.zfill(3)}-*.md"
    matches = sorted(pratiques_dir.glob(pattern))
    if not matches:
        raise HTTPException(404, "Practice card not found")
    content = matches[0].read_text(encoding="utf-8")
    fm = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)
    if not fm:
        raise HTTPException(500, "Invalid practice file format")
    meta = yaml.safe_load(fm.group(1)) or {}
    body_html = md_to_html(fm.group(2).strip())
    illustration = meta.get("illustration", "")
    if illustration:
        illustration = re.sub(r'^\.\./', '/', illustration)
    return {
        "titre": meta.get("titre", ""),
        "categorie": meta.get("categorie", ""),
        "phase": meta.get("phase", ""),
        "difficulte": meta.get("difficulte", ""),
        "duree": meta.get("duree", ""),
        "participants": meta.get("participants", ""),
        "icone_code": meta.get("icone_code", ""),
        "source": meta.get("source", ""),
        "url": meta.get("url", ""),
        "pdf": meta.get("pdf", ""),
        "illustration": illustration,
        "body_html": body_html,
    }
