# AGENTS.md — Facilito

## Identity

Python/FastAPI app for collaborative workshop design. Primary UI is an LLM agent (function-calling) that recommends facilitation practices via ChromaDB RAG and acts on SQLite session data.

## Commands

```bash
# Start server (from repo root)
python -m Agent.Main.main --openai      # GPT-4o (default)
python -m Agent.Main.main --deepseek    # DeepSeek

# RAG initialization (one-time, after cloning)
python -m Agent.Tools.RAG.init_rag            # creates data/chroma_db + data/facilito.db
python -m Agent.Tools.RAG.init_rag --reinit   # wipe and rebuild

# Tests — run after every code change before reporting done
python -m pytest test/unitaires/ -v                          # 118 tests, 9 files
python -m pytest test/unitaires/ -v --cov=Agent --cov-report=term-missing

# LLM evaluation (server must be running)
python test/llm_judge/run_judge.py --openai

# Docker
docker build -t facilito:v1 . && docker-compose up -d
```

## Setup

```bash
cp Agent/.env.example Agent/.env   # fill OPENAI_API_KEY and DEEPSEEK_API_KEY
pip install -r requirements.txt && pip install -r requirements-test.txt
python -m Agent.Tools.RAG.init_rag
```

Embeddings **always** use OpenAI `text-embedding-3-small` regardless of `--openai`/`--deepseek` mode.

## Key Rules

- **Never modify, disable, or delete a test** without explicit approval. Fix production code instead.
- Tests are isolated (in-memory SQLite per test, RAG cache cleared, agent memory reset) — no API calls, LLM is mocked.
- The agent **cannot** delete sessions, participants, teams, or facilitators (no tools exist for it; enforced in system prompt).
- `_BASE_DIR` resolution: `Agent/Tools/*.py` → `parents[3]` to root; `Agent/Main/*.py` → `parents[2]`.

## Architecture Highlights

| Layer | Location | Role |
|---|---|---|
| Server + agent loop | `Agent/Main/main.py` | FastAPI app factory, all REST routes, agent dispatch, PDF export |
| SQLite CRUD | `Agent/Tools/Database/` | facilitators, sessions, participants, clients_teams, analytics |
| RAG | `Agent/Tools/RAG/` | ChromaDB init + semantic search (OpenAI embeddings) |
| Memory | `Agent/Tools/Memory/store.py` | In-memory deque (10 exchanges), `build_system_prompt()` |
| LLM providers | `Agent/LLM/` | Abstract base → OpenAI / DeepSeek |
| Config | `Agent/Config/` | `app_config.yaml` (paths, ports), `special_practices.yaml` (Accueil/Pause/Déjeuner/Débriefing) |
| Frontend | `Agent/Main/static/` | Single `index.html` SPA (no framework) |
| Content | `pratiques/` | 73 Markdown files with YAML frontmatter — RAG source |

## Database

SQLite at `data/facilito.db`. Key relations:
- `sessions` → `facilitators` (FK); status: draft/confirmed/finished
- `session_practices` — ordered list with `position`, `duration_minutes`, `source` (rag|special)
- `session_participants`, `session_teams`, `session_clients` — M2M joins
- `team_participants` — M2M for teams
- `get_session_context(session_id)` returns full object (facilitator, participants, practices, total_duration)

## Agent Loop

In `main.py:agent_chat()`: build system prompt from session context → prepend 10-exchange history → call LLM with 16 tool schemas → dispatch tool calls (max 10 iterations) → return `{reply, tool_results}`.

`_SESSION_SCOPED` tools (`get_session_context`, `add_practice`, `remove_practice`, `reorder_practice`, `update_practice_duration`, `add_participant_to_session`, `add_team_to_session`): the agent's `session_id` arg is overridden with the one from the HTTP request for safety.

Resolution markers in responses: `||RÉSOLU||` (done) or `||NON_RÉSOLU||` (unresolved).

## Docker

`Dockerfile` (python:3.11-slim, port 8000) + `docker-compose.yml` (maps 8001:8000, binds `./data:/app/data`). RAG must be initialized **locally** first — the bind mount shares `data/chroma_db` + `data/facilito.db` with the container.
