"""Dashboard REST routes (analytics, KPIs, logs, ratings, cost config)."""

from fastapi import APIRouter

from Agent.Tools.Database.analytics import get_kpis, get_logs, log_rating, get_cost_config, set_cost_config
from Agent.Main.models import RatingBody, CostConfigBody

router = APIRouter(tags=["dashboard"])


@router.get("/api/dashboard/kpis")
def dashboard_kpis():
    return get_kpis()


@router.get("/api/dashboard/logs")
def dashboard_logs(types: str = "", limit: int = 200):
    type_list = [t.strip() for t in types.split(",") if t.strip()] or None
    return get_logs(types=type_list, limit=limit)


@router.post("/api/dashboard/rate")
def dashboard_rate(body: RatingBody):
    log_rating(body.session_id, body.rating)
    return {"ok": True}


@router.get("/api/dashboard/config")
def dashboard_config():
    return get_cost_config()


@router.post("/api/dashboard/config")
def dashboard_config_update(body: CostConfigBody):
    set_cost_config(body.cost_in, body.cost_out)
    return get_cost_config()
