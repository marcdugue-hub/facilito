"""Pydantic request models for all REST endpoints."""

from pydantic import BaseModel


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


class RatingBody(BaseModel):
    session_id: int
    rating: int


class CostConfigBody(BaseModel):
    cost_in: float
    cost_out: float


class ToggleBody(BaseModel):
    enabled: bool
