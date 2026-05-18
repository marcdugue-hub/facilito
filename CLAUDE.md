# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Facilito is a Python/FastAPI web application that helps facilitators design collaborative workshops. An AI agent (LLM with function-calling) is the primary interaction mode. The 73 facilitation practices in `pratiques/` power a ChromaDB RAG. SQLite stores facilitators, sessions, participants, teams, and clients.

## Commands

```bash
# First-time setup: initialize the RAG from pratiques/
python -m Agent.Tools.RAG.init_rag          # creates chroma_db/
python -m Agent.Tools.RAG.init_rag --reinit  # wipe and rebuild

# Start the server (from Facilito/ root)
python -m Agent.Main.main --openai     # default, uses GPT-4o
python -m Agent.Main.main --deepseek   # uses DeepSeek LLM
# → http://localhost:8000
```

Keys go in [Agent/.env](Agent/.env): `OPENAI_API_KEY` and `DEEPSEEK_API_KEY`. Embeddings always use OpenAI `text-embedding-3-small` regardless of LLM mode.

## Unit Tests — MANDATORY

**Claude Code must run the unit test suite after every code change, before reporting a task as complete.** Tests must pass before any Docker build or commit.

```bash
python -m pytest test/unitaires/ -v
```

118 tests across 9 files. LLM is mocked — no API calls are made. Each test gets an isolated in-memory SQLite database. If any test fails after a change, fix the root cause before proceeding.

**Never modify, disable, or delete any test without explicit user approval.** If a code change causes a test to fail, fix the production code — not the test.

## Architecture

```
Agent/
├── .env                        # API keys
├── Config/
│   ├── app_config.yaml         # host, port, model names, DB/Chroma paths
│   └── special_practices.yaml  # Accueil, Pause, Débriefing definitions
├── LLM/
│   ├── base.py                 # abstract LLMProvider (chat method)
│   ├── openai_provider.py      # GPT-4o via openai SDK
│   └── deepseek_provider.py    # DeepSeek via openai SDK + custom base_url
├── Main/
│   ├── main.py                 # FastAPI app factory, all routes, agent loop, PDF export
│   └── static/                 # SPA (index.html, style.css, app.js)
└── Tools/
    ├── Database/
    │   ├── schema.py            # SQLite connection + CREATE TABLE (init_db())
    │   ├── facilitators.py      # list/create/get facilitators
    │   ├── sessions.py          # sessions CRUD + session_practices management + get_session_context()
    │   ├── participants.py      # participants CRUD + session/team membership
    │   └── clients_teams.py     # clients + teams CRUD
    ├── Memory/
    │   └── store.py             # in-memory deque (10 exchanges), build_system_prompt()
    └── RAG/
        ├── init_rag.py          # parse pratiques/*.md → embed → Chroma
        └── search.py            # search_practices(query, n) via OpenAI embeddings
```

`_BASE_DIR` in each module resolves to the `Facilito/` root:
- Files in `Agent/Tools/XXX/` → `Path(__file__).resolve().parents[3]`
- Files in `Agent/Main/` → `Path(__file__).resolve().parents[2]`

## Database Schema

SQLite file at `facilito.db` (root). Key relations:
- `sessions` → `facilitators` (FK)
- `session_practices` — ordered list with `position`, `duration_minutes`, `source` ('rag'|'special')
- `session_participants`, `session_teams`, `session_clients` — many-to-many joins
- `team_participants` — many-to-many for teams

`get_session_context(session_id)` in [sessions.py](Agent/Tools/Database/sessions.py) returns the full object (facilitator, participants, practices, total_duration) passed to the agent system prompt.

## Agent

The agent loop is in `main.py:agent_chat()`. It:
1. Builds a system prompt from `build_system_prompt(session_context)` — includes session state
2. Prepends the 10-exchange history from `store.py`
3. Calls the LLM provider with `TOOLS` (11 function schemas)
4. Dispatches tool calls via `_dispatch_tool(name, args)` in a loop (max 10 iterations)
5. Returns final text response + list of `tool_results` to the frontend

The agent **cannot** delete sessions, participants, teams, or facilitators (enforced in the system prompt and by not providing delete tools).

## Frontend SPA

Single [index.html](Agent/Main/static/index.html) with 4 screen sections toggled by JS:
- `screen-facilitators`, `screen-sessions`, `screen-session`, `screen-clients`

Layout: `display: grid; grid-template-columns: 2fr 1fr` (main | agent panel). On mobile (`≤768px`) the agent panel is hidden and a floating bubble (`#agent-bubble`) opens `#agent-panel-mobile`.

When the agent modifies session data (practice added/removed/reordered, participants changed), the JS calls `openSession(id)` to refresh state.

## Content (pratiques/)

73 Markdown files, each with YAML frontmatter (`id`, `titre`, `categorie`, `phase`, `difficulte`, `duree`, `participants`, `icone_code`) and fixed body sections (Objectif, Valeur ajoutée, Résumé, Materiel, Déroulé, Point de vigilance, Variante, Source).

Category → icon prefix: ICE (Briser la glace), PBM (Résoudre), VIZ (Partager la vision), DEC (Prioriser), ID (Générer des idées), BIL (S'améliorer).
