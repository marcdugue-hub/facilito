"""Client REST routes."""

from fastapi import APIRouter

from Agent.Tools.Database import clients_teams as db_ct
from Agent.Main.models import ClientCreate

router = APIRouter(tags=["clients"])


@router.get("/api/clients")
def get_clients():
    return db_ct.list_clients()


@router.post("/api/clients", status_code=201)
def post_client(body: ClientCreate):
    return db_ct.create_client(body.name)
