"""Team REST routes."""

from fastapi import APIRouter

from Agent.Tools.Database import clients_teams as db_ct
from Agent.Tools.Database import participants as db_par
from Agent.Tools.Database import sessions as db_ses
from Agent.Main.models import TeamAdd, TeamCreate, TeamParticipantAdd

router = APIRouter(tags=["teams"])


@router.post("/api/sessions/{sid}/teams")
def post_team_to_session(sid: int, body: TeamAdd):
    added = db_ses.add_team_to_session(sid, body.team_id)
    return {"added": added}


@router.get("/api/teams")
def get_teams(client_id: int = None):
    return db_ct.list_teams(client_id)


@router.post("/api/teams", status_code=201)
def post_team(body: TeamCreate):
    return db_ct.create_team(body.name, body.client_id)


@router.get("/api/teams/{tid}/participants")
def get_team_participants(tid: int):
    return db_ct.get_team_participants(tid)


@router.get("/api/teams/{tid}/orphan-participants")
def get_team_orphan_participants(tid: int):
    return db_ct.get_team_participants_not_in_sessions(tid)


@router.post("/api/teams/{tid}/participants", status_code=201)
def post_team_participant(tid: int, body: TeamParticipantAdd):
    if body.participant_id:
        db_ct.add_participant_to_team(tid, body.participant_id)
        return db_par.get_participant(body.participant_id)
    p = db_par.create_participant(body.first_name, body.last_name, body.email, body.role)
    db_ct.add_participant_to_team(tid, p["id"])
    return p


@router.delete("/api/teams/{tid}")
def delete_team_route(tid: int, delete_orphan_participants: bool = False):
    if delete_orphan_participants:
        orphans = db_ct.get_team_participants_not_in_sessions(tid)
        for p in orphans:
            db_par.delete_participant(p["id"])
    db_ct.delete_team(tid)
    return {"ok": True}
