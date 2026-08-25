# crucible

Arena

A live arena where LLM agents compete on a task in real time, streamed to the browser so you watch them reason, act, and react — with a trajectory-scoring layer underneath that turns every match into measurable data.

The visible product is the live match. The quiet differentiator is the instrumentation: which strategy, prompt, or model actually wins, and why.

Status: all Phase 5 repository work is complete. Publishing the live URL and recording the demo
remain deployment-owner steps. See
`docs/multi_agent_arena_build_plan.md` for the full plan and phase breakdown.

## Demo

- **Live app:** `https://<your-vercel-domain>` (add after following [`DEPLOYMENT.md`](DEPLOYMENT.md))
- **60-second recording:** follow [`docs/DEMO.md`](docs/DEMO.md), then add the published recording here
- **Results:** [`docs/RESULTS.md`](docs/RESULTS.md) documents the reproducible scripted baseline and the controlled LLM experiment protocol

What it does
Runs a match: two (or more) agents act turn-by-turn inside a pluggable environment.
Streams reasoning live — each agent's thinking fills in token-by-token as it decides, then its action lands and the environment updates.
Scores every match two ways: objective payoffs where the environment has them, and a rubric-based LLM judge for open-ended scenarios that don't.
Persists full trajectories so matches can be replayed, and aggregated into win-rates by strategy and model.
Runs repeated negotiation tournaments with bounded concurrency, fixed seeds, and alternating seats.
Environments
Environment	Type	Scoring
Negotiation (flagship)	Multi-issue bargaining, two agents split a pool with private valuations	Objective payoffs
Role-play	Two agents play defined roles (e.g. interviewer vs. interviewee), optionally seeded with context data (JD + CV)	Rubric LLM judge
Debate (optional third)	Two agents argue a motion	Rubric LLM judge

New environments drop in behind a single Environment interface — a scenario is a class plus prompts and (optionally) seed data, not new plumbing.

Architecture
┌────────────┐   WebSocket (single-writer event stream)   ┌────────────┐
│  Frontend  │ ◄──────────────────────────────────────────│  Backend   │
│ Vite+React │        match_started / reasoning_delta /    │  FastAPI   │
│            │        action / state_update / score_update │            │
│ live match │        / match_ended / error               │ orchestrator
│ + replay   │───────────────────────────────────────────►│ + agents   │
│ + leaderbd │        start_match / cancel_match           │ + envs     │
└────────────┘                                             └─────┬──────┘
                                                                 │
                                                          ┌──────▼──────┐
                                                          │   SQLite    │
                                                          │ trajectories│
                                                          │  + scores   │
                                                          └─────────────┘
                                                    Agents → Anthropic API
Backend (backend/) — Python + FastAPI (async, native WebSocket), Anthropic SDK for agents, SQLite for persistence. Owns the environments, the match orchestrator, the agents, and the judge.
Frontend (frontend/) — Vite + React + TypeScript. Owns the live match view, trajectory replay, and the aggregate leaderboard.
Contract — a frozen event schema + interfaces shared by both sides. This is the keystone; see below.
Tech stack

Python · FastAPI · SQLite (SQLModel) · WebSocket · Vite · React · TypeScript · Tailwind · Anthropic API. Deliberately zero-infra (no Redis, no Postgres, no SSR) to stay finishable and deployable.

The contract comes first

This repo is built contract-first so the backend and frontend can be developed in parallel without colliding. Before feature work starts, the shared event schema, the Environment / Agent interfaces, and the data model are defined once and frozen:

Python source of truth: backend/app/contract/ (types, ABCs, DB models)
TypeScript mirror: frontend/src/contract/ (event + action types)

Changing the contract is a deliberate, coordinated act — both sides re-sync to it together. A silent edit on one side desyncs the two and only surfaces at integration, which is the most painful place to find it. If you need a new event field, announce it and update both mirrors in the same change.

Repo layout
arena/
├── README.md
├── docs/
│   └── BUILD_PLAN.md          # full plan + phases (source of truth for what to build)
├── backend/
│   ├── app/
│   │   ├── contract/          # FROZEN: event schema, Environment/Agent interfaces, DB models
│   │   ├── environments/      # negotiation, role_play, …
│   │   ├── agents/            # scripted (dummy) + Claude-backed agents
│   │   ├── orchestrator.py    # runs a match, emits events
│   │   ├── judge/             # rubric LLM-judge scoring
│   │   ├── api/               # REST + WebSocket routes
│   │   └── db.py
│   ├── tests/
│   └── requirements.txt       # pinned
└── frontend/
    ├── src/
    │   ├── contract/          # FROZEN: TS mirror of the event/action schema
    │   ├── match/             # live match view (the wow)
    │   ├── replay/            # trajectory replay
    │   ├── leaderboard/       # aggregate win-rates
    │   └── lib/ws.ts          # socket client (+ mock for frontend-first dev)
    └── package.json
Getting started

Requires Python 3.11+, Node 20+, and an ANTHROPIC_API_KEY.

Backend

bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # set ANTHROPIC_API_KEY
uvicorn app.main:app --reload

Frontend

bash
cd frontend
npm install
npm run dev

The frontend can run against a mock WebSocket that replays canned events in the contract's shape, so the live match view can be built before the backend streams real matches. Point it at the real backend once matches stream.

Deployment

Backend on Railway, frontend on Vercel — this is a monorepo, so each service's root directory must be set explicitly in that platform's project settings.

Use the step-by-step production checklist in [`DEPLOYMENT.md`](DEPLOYMENT.md), including the volume,
environment-variable, CORS, security, and post-deploy verification requirements.

Railway (backend)
- Root directory: `backend`
- Config: `backend/railway.toml` (start command, healthcheck at `/health`)
- Env vars: `ANTHROPIC_API_KEY`, `JUDGE_MODEL`, `ARENA_DB_PATH` (point at a mounted Railway volume, not the ephemeral filesystem — SQLite data is otherwise lost on every redeploy), `ALLOWED_ORIGINS` (the deployed Vercel URL)

Vercel (frontend)
- Root directory: `frontend`
- Framework preset: Vite (auto-detected)
- Env vars: `VITE_WS_URL` (the Railway backend's `wss://` WebSocket URL — Vercel is serverless and can't host the backend's long-lived WebSocket connection itself), `VITE_API_URL` (the Railway backend's `/api` URL)

Build order (short version)
Scaffold — both apps boot empty and green; commit the skeleton.
Freeze the contract — event schema + interfaces + DB models, Python and TS mirrors.
Backend, dummy agents first — negotiation env + orchestrator run a full match with scripted agents (no LLM), writing a complete trajectory. De-risk the loop before adding LLM latency/cost.
Backend, real agents + streaming — Claude agents, live reasoning over the single-writer socket, clean cancellation.
Frontend, in parallel — live match view against the mock socket, then swap to the real one.
Instrumentation — replay, rubric judge, aggregate leaderboard (with honest match counts).
Polish — role-play environment, tournament mode (bounded concurrency), deploy, demo.

Full detail, exit criteria per phase, and the parallel Claude Code / Codex split are in
`docs/multi_agent_arena_build_plan.md`.

Principles
Commit at every green state — a working point to fall back to always exists.
One writer to the socket — all events serialize through a single writer draining a queue; never concurrent sends from parallel agent tasks.
Validate agent actions — agents emit malformed JSON / illegal moves; validate, retry once, forfeit the turn. A bad action never crashes the match loop.
Never leak private state through environment updates — an environment's `public_view` excludes valuations and cross-role private context, and redaction is enforced at the environment boundary rather than the UI. The current product is explicitly a spectator/evaluation UI: agent-authored reasoning is intentionally streamed and retained for replay, so an agent may mention information from its own private observation there. Do not expose the reasoning feed to opposing participants without adding a separate participant-safe event and replay policy.
Honest measurement — LLM nondeterminism means single matches prove nothing; aggregate claims show match counts and control what they can. This rigor is what makes the arena more than a toy.
