"""
Facilito — FastAPI server
Launch: python -m Agent.Main.main [--openai | --deepseek]
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

_BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BASE_DIR))
load_dotenv(_BASE_DIR / "Agent" / ".env")

from Agent.Config.config import load_config, get_project_root
from Agent.LLM.provider_factory import build_provider
from Agent.Tools.Database.schema import init_db

from Agent.Main.routes.facilitators import router as facilitators_router
from Agent.Main.routes.sessions import router as sessions_router
from Agent.Main.routes.practices import router as practices_router
from Agent.Main.routes.participants import router as participants_router
from Agent.Main.routes.teams import router as teams_router
from Agent.Main.routes.clients import router as clients_router
from Agent.Main.routes.dashboard import router as dashboard_router
from Agent.Main.routes.config import router as config_router
from Agent.Main.routes.settings import router as settings_router
from Agent.Main.routes.agent import router as agent_router
from Agent.Main.routes.meta import router as meta_router


def create_app(llm_mode: str = "openai") -> FastAPI:
    provider = build_provider(llm_mode)
    app = FastAPI(title="Facilito")

    app.state.provider = provider
    app.state.llm_mode = llm_mode

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    illustrations_dir = get_project_root() / "illustrations"
    mascotte_dir = get_project_root() / "Mascotte"
    app.mount("/illustrations", StaticFiles(directory=str(illustrations_dir)), name="illustrations")
    app.mount("/mascotte", StaticFiles(directory=str(mascotte_dir)), name="mascotte")

    init_db()

    app.include_router(meta_router)
    app.include_router(facilitators_router)
    app.include_router(sessions_router)
    app.include_router(practices_router)
    app.include_router(participants_router)
    app.include_router(teams_router)
    app.include_router(clients_router)
    app.include_router(dashboard_router)
    app.include_router(config_router)
    app.include_router(settings_router)
    app.include_router(agent_router)

    return app


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="Facilito server")
    parser.add_argument("--openai", action="store_true", help="Use OpenAI")
    parser.add_argument("--deepseek", action="store_true", help="Use DeepSeek (default)")
    args = parser.parse_args()

    mode = "deepseek" if args.deepseek else ("openai" if args.openai else "deepseek")
    cfg = load_config()
    host = os.environ.get("APP_HOST", cfg["app"]["host"])
    port = int(os.environ.get("APP_PORT", cfg["app"]["port"]))
    print(f"Starting Facilito in {mode.upper()} mode on http://{host}:{port}")

    app = create_app(llm_mode=mode)
    uvicorn.run(app, host=host, port=port)
