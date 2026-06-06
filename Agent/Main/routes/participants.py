"""Participant REST routes (session-scoped + global)."""

from fastapi import APIRouter, HTTPException

from Agent.Tools.Database import participants as db_par
from Agent.Main.models import ParticipantAdd, ParticipantUpdate

router = APIRouter(tags=["participants"])


@router.get("/api/sessions/{sid}/participants")
def get_participants(sid: int):
    return db_par.get_session_participants(sid)


@router.post("/api/sessions/{sid}/participants", status_code=201)
def post_participant(sid: int, body: ParticipantAdd):
    if body.participant_id:
        db_par.add_participant_to_session(sid, body.participant_id)
        return db_par.get_participant(body.participant_id)
    p = db_par.create_participant(body.first_name, body.last_name, body.email, body.role)
    db_par.add_participant_to_session(sid, p["id"])
    return p


@router.delete("/api/sessions/{sid}/participants/{pid}")
def del_participant(sid: int, pid: int):
    db_par.remove_participant_from_session(sid, pid)
    return {"ok": True}


@router.get("/api/participants")
def get_all_participants():
    return db_par.list_participants()


@router.get("/api/participants/{pid}")
def get_participant_route(pid: int):
    p = db_par.get_participant(pid)
    if not p:
        raise HTTPException(404)
    return p


@router.patch("/api/participants/{pid}")
def patch_participant(pid: int, body: ParticipantUpdate):
    p = db_par.update_participant(pid, **body.model_dump())
    if not p:
        raise HTTPException(404)
    return p


@router.delete("/api/participants/{pid}")
def delete_participant_route(pid: int):
    db_par.delete_participant(pid)
    return {"ok": True}
