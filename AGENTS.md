# AGENTS.md — Facilito

## Identity

Python/FastAPI app for collaborative workshop design. Primary UI is an LLM agent (function-calling) that recommends facilitation practices via ChromaDB RAG and acts on SQLite session data.

## Commands

```bash
# Start server (from repo root)
python -m Agent.Main.main --openai      # GPT-4o (default)
python -m Agent.Main.main --deepseek    # DeepSeek

# RAG initialization (one-time, after cloning)
python -m Agent.Tools.RAG.init_rag              # creates data/chroma_db (OpenAI embeddings) + data/facilito.db
python -m Agent.Tools.RAG.init_rag --local      # creates data/chroma_db_local (sentence-transformers, no API key)
python -m Agent.Tools.RAG.init_rag --reinit     # wipe and rebuild
python -m Agent.Tools.RAG.init_rag --reinit --local  # wipe and rebuild local

# Tests unitaires — run after every code change before reporting done
python -m pytest test/unitaires/ -v                          # 127 tests across 9 files
python -m pytest test/unitaires/ -v --cov=Agent --cov-report=term-missing

# Tests d'intégration — run before merging / after major changes — 7 fichiers, ~75 tests
python -m pytest test/integration/ -v                        # tous les tests d'intégration
python -m pytest test/integration/ -v -k "not openai and not deepseek"  # sans LLM (DB + web + PDF + RAG local)
python -m pytest test/integration/ -v -k "openai or deepseek"           # seulement les tests LLM

# Les tests d'intégration LLM (openai/deepseek) utilisent de vraies clés API.
# - Si une clé est invalide → les tests marqués correspondants sont ignorés.
# - Si les deux clés sont invalides → l'utilisateur est invité à confirmer.
# Prérequis : RAG local initialisé (python -m Agent.Tools.RAG.init_rag --local)
# Couverture : LLM (OpenAI + DeepSeek), RAG (local + OpenAI), interface web, export PDF, base de données

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
- Tests are isolated (in-memory SQLite per test, RAG cache cleared, agent memory reset) — no API calls, LLM is mocked. `pytest.ini` configures `testpaths = test`, `-v --tb=short`.
- The agent **cannot** delete sessions, participants, teams, or facilitators (no tools exist for it; enforced in system prompt).
- `_BASE_DIR` resolution: `Agent/Tools/*.py` → `parents[3]` to root; `Agent/Main/*.py` → `parents[2]`.
- See also `CLAUDE.md` (Claude Code guidance) and `test/audit-code.md` (34-point code quality audit).

## Architecture Highlights

| Layer | Location | Role |
|---|---|---|
| Server + agent loop | `Agent/Main/main.py` | FastAPI app factory, 39 REST routes, agent dispatch, PDF export (weasyprint) |
| SQLite CRUD | `Agent/Tools/Database/` | facilitators, sessions (with `start_time`), participants, clients, teams, analytics (events, ratings, cost config, app settings) |
| Security | `Agent/Tools/security.py` | Injection detection (6 regex), PII masking (email/phone/IBAN), rate limiting (10 req/s), LLM retry with exponential backoff |
| Errors | `Agent/Tools/erreur.py` | 7 custom exceptions (FacilitoError, InvalidUserInputError, InjectionDetectedError, RateLimitError, LLMTimeoutError, InvalidAPIKeyError, ExternalServiceError) |
| RAG | `Agent/Tools/RAG/` | ChromaDB init + semantic search (OpenAI embeddings); dual collection (OpenAI + local sentence-transformers) |
| Embedding | `Agent/Tools/RAG/embedder.py` | `get_embeddings()` (local `paraphrase-multilingual-MiniLM-L12-v2`) and `get_openai_embeddings()` (`text-embedding-3-small`) |
| Memory | `Agent/Tools/Memory/store.py` | In-memory deque (10 exchanges) — conversation history |
| Prompts | `Agent/Prompts/system_prompt.py` | `build_system_prompt()` with session context injection (extracted from Memory) |
| Observability | `Agent/Observability/langfuse_handler.py` | LangFuse tracing, LLM generation tracking, cost logging (moved from Tools/) |
| LLM providers | `Agent/LLM/` | Abstract base → OpenAI (`gpt-4o`) / DeepSeek (`deepseek-chat`) |
| Config | `Agent/Config/` | `app_config.yaml` (paths, ports, model names), `special_practices.yaml` (Accueil/Pause/Déjeuner/Débriefing) |
| Frontend | `Agent/Main/static/` | SPA: `index.html`, `app.js` (vanilla JS IIFE, 4 screens), `style.css` (responsive grid) |
| Content | `pratiques/` | 73 Markdown files with YAML frontmatter — RAG source |

## Database

SQLite at `data/facilito.db`. Auto-created by `init_db()` in `Agent/Tools/Database/schema.py`.

**Core relations:**
| Table | Key columns | Notes |
|---|---|---|
| `facilitators` | `id`, `name` | |
| `sessions` | `id`, `facilitator_id` (FK), `title`, `date`, `start_time`, `objective`, `status` (draft/confirmed/finished), `created_at` | `start_time` added via migration |
| `session_practices` | `id`, `session_id` (FK), `practice_id`, `source` (rag\|special), `titre`, `duration_minutes`, `position` | Ordered practice list |
| `session_participants` | `session_id`, `participant_id` | M2M join |
| `session_teams` | `session_id`, `team_id` | M2M join (tracks imported teams) |
| `session_clients` | `session_id`, `client_id` | M2M join |
| `participants` | `id`, `first_name`, `last_name`, `email`, `role` | |
| `clients` | `id`, `name` | Organizations |
| `teams` | `id`, `name`, `client_id` (FK) | |
| `team_participants` | `team_id`, `participant_id` | M2M join |

**Analytics & config:**
| Table | Key columns | Notes |
|---|---|---|
| `agent_events` | `id`, `timestamp`, `session_id`, `event_type` (llm/rag/db/resolution), `summary`, `payload` (JSON), `tokens_in`, `tokens_out`, `duration_ms`, `resolved`, `fallback` | Event log |
| `agent_ratings` | `id`, `timestamp`, `session_id`, `rating` (INT) | User satisfaction |
| `cost_config` | `key` (cost_in/cost_out), `value` (REAL) | Defaults: 1.5 / 2.5 per 1M tokens |
| `app_settings` | `key`, `value` | Default: `voice_mode` = 'off' |

`get_session_context(session_id)` returns full object (facilitator, participants, practices, total_duration).

## Agent Loop

In `main.py:agent_chat()`: validate (rate limit, injection, length) → load session context → `build_system_prompt()` → prepend 10-exchange history from in-memory deque → call LLM with **16 tool schemas** (function-calling, `tool_choice: "auto"`) → dispatch tool calls via `_dispatch_tool()` (max 10 iterations) → log events to `agent_events` → return `{reply, tool_results}`.

**16 tools:** `list_facilitators`, `search_practices`, `get_session_context`, `create_session`, `update_session`, `add_practice`, `remove_practice`, `reorder_practice`, `update_practice_duration`, `create_participant`, `add_participant_to_session`, `add_team_to_session`, `create_client`, `create_team`, `list_clients`, `list_teams`.

`_SESSION_SCOPED` tools (`get_session_context`, `update_session`, `add_practice`, `remove_practice`, `reorder_practice`, `update_practice_duration`, `add_participant_to_session`, `add_team_to_session`): the agent's `session_id` arg is overridden with the one from the HTTP request for safety.

Resolution markers in responses: `||RÉSOLU||` (done) or `||NON_RÉSOLU||` (unresolved).

## Docker

`Dockerfile` (python:3.11-slim, CPU-only `torch==2.12.0`, weasyprint deps, curl healthcheck) + `docker-compose.yml` (maps 8001:8000, binds `./data:/app/data` + `~/.cache/huggingface:/root/.cache/huggingface`, defaults to `--deepseek`). RAG must be initialized **locally** first — the bind mount shares `data/chroma_db` + `data/facilito.db` with the container.

## Static Assets

- `illustrations/` — 51 practice illustration images
- `Mascotte/` — 17 mascot images for the UI

## LLM Evaluation

`test/llm_judge/run_judge.py` — sends 20 questions (9 categories) to the running agent, scores responses with a judge LLM (GPT-4o or DeepSeek) on pertinence/fidélité/cohérence (1-5), generates Markdown report in `test/llm_judge/reports/`.
