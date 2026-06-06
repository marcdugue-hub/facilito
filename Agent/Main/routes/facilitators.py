"""Facilitator REST routes."""

from fastapi import APIRouter, HTTPException

from Agent.Tools.Database import facilitators as db_fac
from Agent.Tools.Database import sessions as db_ses
from Agent.Main.models import FacilitatorCreate

router = APIRouter(tags=["facilitators"])


@router.get("/api/facilitators")
def get_facilitators():
    return db_fac.list_facilitators()


@router.post("/api/facilitators", status_code=201)
def post_facilitator(body: FacilitatorCreate):
    return db_fac.create_facilitator(body.name)


@router.get("/api/facilitators/{fid}")
def get_facilitator(fid: int):
    f = db_fac.get_facilitator(fid)
    if not f:
        raise HTTPException(404)
    return f


@router.delete("/api/facilitators/{fid}", status_code=204)
def delete_facilitator_route(fid: int):
    if not db_fac.delete_facilitator(fid):
        raise HTTPException(404)


@router.get("/api/facilitators/{fid}/sessions")
def get_facilitator_sessions(fid: int):
    return db_ses.list_sessions(fid)
