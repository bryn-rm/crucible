# Deployment checklist

Backend on Railway, frontend on Vercel. Each service's root directory must be set
explicitly in that platform's project settings, since this is a monorepo.

## Railway (backend)

- Root directory: `backend`
- Config: `backend/railway.toml` — builder `NIXPACKS`, start command
  `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, healthcheck at `/health`.
- **Volume:** attach a persistent volume and point `ARENA_DB_PATH` at a file inside it.
  Without this, `ARENA_DB_PATH` falls back to `arena.db` on the ephemeral container
  filesystem and match history is lost on every redeploy.
- Env vars:
  - `ANTHROPIC_API_KEY` — required for Claude agents and the judge.
  - `JUDGE_MODEL` — optional, defaults to `claude-sonnet-4-20250514`.
  - `ARENA_DB_PATH` — path to the SQLite file on the mounted volume.
  - `ALLOWED_ORIGINS` — comma-separated list of allowed CORS origins; must include the
    deployed Vercel URL. Defaults to `http://localhost:5173` if unset, which will block
    the production frontend.

## Vercel (frontend)

- Root directory: `frontend`
- Framework preset: Vite (auto-detected)
- Env vars:
  - `VITE_WS_URL` — the Railway backend's `wss://` WebSocket URL. Vercel is serverless
    and can't host the backend's long-lived WebSocket connection itself.
  - `VITE_API_URL` — the Railway backend's `/api` URL.

## Security

- `ALLOWED_ORIGINS` must be pinned to the real Vercel origin(s) in production — never `*`.
- Don't commit `.env` files or API keys; set them through each platform's dashboard.

## Post-deploy verification

1. `GET /health` on the Railway URL returns 200.
2. Open the Vercel URL, start a match, and confirm live events stream over the WebSocket.
3. Confirm a completed match's row survives a Railway redeploy (volume is durable).
4. Confirm a request from an origin *not* in `ALLOWED_ORIGINS` is rejected by CORS.
