# Multi-Agent Arena — Build Plan

## Build status

- **Phase 0 — Complete.** The mirrored Python/TypeScript event and action contracts, pluggable
  environment/agent interfaces, and SQLModel persistence models are in place.
- **Phase 0.5 — Complete.** Railway/Vercel deployment configuration, health and WebSocket routes,
  environment-driven URLs, CORS, and persistent SQLite path configuration are established.
- **Phase 1 — Complete.** The negotiation environment, deterministic scripted agents, resilient
  orchestrator loop, public-state redaction, scoring, and full trajectory persistence are covered by
  backend tests.
- **Phase 2 — Complete.** Claude and OpenAI negotiation agents stream model output through the
  single-writer WebSocket path, use shared structured-action parsing, retry invalid actions, select
  providers by model/configuration, and support cancellation and recoverable errors.
- **Phase 3 — Complete.** The responsive frontend now includes agent/model/strategy setup, live
  connection and match controls, streaming reasoning panels, latest actions, negotiation state and
  offer history, running scores, and explicit error/terminal states.
- **Phases 4–5 — Not started.** History/replay APIs, judge scoring, aggregation/leaderboards,
  role-play, tournaments, and final demo polish remain.

A live arena where LLM agents compete on a task in real time, streamed to a browser so you *watch*
them reason, act, and react — with a trajectory-scoring layer underneath that turns each match into
measurable data. The visible product is the live match; the quiet differentiator is the
instrumentation (which strategy/model wins, and why).

**Why this project:** it's the complement to your other work — real-time and concurrent where Felix
is stateful, visually demoable in 60 seconds where a thesis is a document, and it exercises
streaming/concurrency as a fresh competency. The eval layer is present but not the point (it's the
signature, not the pitch).

**Thesis relationship (important boundary):** this is *not* the adversarial-eval thesis, and must
not quietly become it. It shares DNA — an environment, agents, a judge, trajectory scoring — so it's
a natural sandbox the thesis can later build on. But this is a portfolio/fun build with a loose
scope you control; the thesis needs a supervisor-agreed research question and rigor. Keep them
separate repos. If they converge later, that's a bonus, not a plan.

---

## Core design decisions

1. **The environment is pluggable; ship one done well.** Define a clean `Environment` interface so
   scenarios (negotiation, debate, role-play, market, game) drop in behind it. v1 flagship:
   **multi-issue negotiation** (clear payoffs, observable strategy, natural adversarial dynamic).
   Two more environments follow in polish — judge-scored **debate** and **role-play scenarios**
   (e.g. interviewer vs. interviewee) — to prove the abstraction generalizes beyond
   objective-payoff games and to exercise the LLM-judge / rubric-scoring path.

2. **Two scoring regimes, by design.** Some environments have *objective* outcomes (negotiation
   payoffs, game wins); others are *open-ended* with no natural score (role-play). The system must
   support both from the start: an objective `score()` on the environment, *and* a rubric-based LLM
   judge that scores a trajectory along defined dimensions. Open-ended scenarios lean entirely on the
   judge — which is the more eval-relevant capability to show, not a weaker one.

3. **Agents stream their reasoning, then act.** Each agent turn produces a *reasoning* stream
   (rendered live as the agent "thinking") followed by a *structured action* (JSON, validated). The
   watching-them-think part is the wow; the structured action is what the environment consumes.
   (In open-ended role-play the "action" is simply the agent's utterance plus any scenario-specific
   structured fields — the same shape, lighter schema.)

4. **One WebSocket, one writer.** All match events (reasoning tokens from multiple agents, state
   changes, scores) flow to the client over a single socket, serialized through a single writer
   draining a queue — never concurrent sends from parallel agent tasks. (This is the exact
   single-writer discipline that bites in any multi-producer streaming system; get it right up front.)

5. **The event schema is the contract, and it's frozen before parallel work starts.** Backend and
   frontend are built against it independently. Changing it mid-build is what breaks a two-agent
   parallel effort, so Phase 0 exists to lock it.

6. **Instrumentation is first-class, not bolted on.** Every match persists a full trajectory
   (per-turn observation, reasoning, action, resulting state) plus objective and/or judge scores;
   aggregate views answer "which agent/strategy/model wins." This is cheap to design in now and
   impossible to reconstruct later — same lesson as the Felix eval telemetry.

7. **Keep infra light.** FastAPI + SQLite + WebSocket + a Vite/React SPA + Anthropic API. No Redis,
   no Postgres, no Next.js SSR — it's an app, not a content site, and zero-infra keeps it deployable
   and finishable. Add Redis pub/sub only if you later want multi-viewer broadcast at scale.

8. **Deploy first, not last.** The current laptop can't run this locally, so there is no localhost
   fallback — Railway (backend) and Vercel (frontend) are decided upfront, not a Phase 5 afterthought,
   and every phase after Phase 0 is built and verified against the live deployment. This is also
   deliberate de-risking: WebSocket-over-cross-origin, CORS, and SQLite-on-ephemeral-disk are exactly
   the issues that hide until "deploy day" — surface them in Phase 0.5, before feature work, not after.

## Tech stack

- **Backend:** Python + FastAPI (async, native WebSocket), the Anthropic SDK for agents.
- **Persistence:** SQLite via SQLModel/SQLAlchemy (matches, trajectories, scores). One file, no infra.
- **Frontend:** Vite + React + TypeScript, a WebSocket client, a light state store (Zustand or
  reducer). Tailwind for speed.
- **Models:** a fast model (e.g. Haiku 4.5) for agents to keep matches cheap; a stronger model
  (e.g. Sonnet 5) for the judge where used. Confirm current model strings against the Anthropic docs
  before wiring — model-as-a-variable is itself an experiment axis, so make it config, not a constant.
- **Deployment:** backend on **Railway** (WebSocket-capable, persistent volume for the SQLite file);
  frontend on **Vercel**. Decided from the start, not deferred to a later phase — see Phase 0.5. All
  development happens against these deployed instances; there is no local dev environment to fall
  back on.

---

## Phase 0 — The contract (build this first; everything depends on it)

One person/tool builds this alone, then it's frozen. It's small and it's the keystone.

**WebSocket event schema** (server → client), a discriminated union on `type`:
- `match_started` — match id, environment name, agent roster (id, label, model, strategy).
- `turn_started` — which agent is acting, turn number.
- `reasoning_delta` — agent id, token/chunk (streamed; many per turn).
- `action` — agent id, the structured action taken (parsed), turn number.
- `state_update` — the new public environment state (whatever the env exposes to viewers).
- `score_update` — running/interim scores.
- `match_ended` — outcome, final scores, reason (agreement / round-limit / error).
- `error` — recoverable/terminal, message.

Client → server is minimal: `start_match` (env + agent configs), `cancel_match`.

**`Environment` interface** (backend):
- `reset() -> State`
- `observe(agent_id) -> Observation` (what that agent sees — includes private info like its own
  valuations, plus public history)
- `legal_actions(agent_id)` / action schema (for validation)
- `step(agent_id, action) -> (new_state, events)` — applies an action, returns state + any emitted events
- `is_terminal(state) -> bool`
- `score(state) -> dict[agent_id, float]` — objective payoffs
- `public_view(state) -> dict` — the redacted state safe to stream to viewers (never leak private info)

**`Agent` interface** (backend):
- `act(observation) -> (reasoning_stream, action)` — streams reasoning, returns a validated action.
- Config: `id, label, model, strategy_prompt, temperature`.

**Data model** (SQLite):
- `matches(id, environment, status, created_at, ended_at, outcome, reason)`
- `match_agents(id, match_id, label, model, strategy, final_score)`
- `turns(id, match_id, agent_id, turn_no, observation_json, reasoning_text, action_json, state_after_json, latency_ms, created_at)`
- `scores(id, match_id, agent_id, dimension, value)` — objective now; judge dimensions later

**Exit criteria:** schema + interfaces + DB models committed as types in both a Python module and a
matching TS types file. Frozen. No feature work has started; this is pure contract.

## Phase 0.5 — Deploy skeleton (before any feature work)

There's no local dev environment on this machine, so the deployed stack has to exist and work
*before* Phase 1 starts — otherwise every later phase discovers its integration problems at the end
instead of the beginning. This phase deploys nothing interesting; it only proves the pipe works.

- Deploy a minimal FastAPI app to **Railway** with one WebSocket endpoint that echoes back whatever
  it receives.
- Deploy a minimal Vite/React SPA to **Vercel** with a "ping" button that opens a WSS connection to
  the Railway URL (via an env var, not a hardcoded host) and shows the echoed response.
- Confirm the round trip actually works over **WSS across origins** — this is where CORS and
  WebSocket-specific proxy/timeout issues on Railway's edge would show up, and they're much cheaper
  to hit now than under Phase 2's real streaming load.
- Attach a **persistent volume** to the Railway service for the SQLite file (Railway's default
  container disk is ephemeral — a redeploy without a volume silently wipes the database). Write one
  row via a throwaway endpoint, trigger a redeploy, confirm the row survived.
- Confirm both services **auto-deploy on push to `main`** (Railway and Vercel both support this
  natively) so that from here on, "ship a change" and "deploy a change" are the same action.

**Exit criteria:** clicking "ping" on the live Vercel URL round-trips a message through the live
Railway WebSocket and back; a row written to SQLite survives a Railway redeploy; pushing to `main`
redeploys both services without manual steps. Nothing from Phase 1 onward is verified locally —
everything is verified against these deployed instances.

## Phase 1 — Backend: environment + orchestrator loop (dummy agents, no LLM)

De-risk the orchestration before adding LLM latency/cost/nondeterminism.

- Implement the **negotiation environment** (spec below).
- Implement the **match orchestrator**: reset env → loop turns → for the active agent, `observe` →
  `agent.act` → validate action → `env.step` → emit events → check terminal → `score`. Handle turn
  order, round limit, malformed-action retry/forfeit.
- Use a **scripted/random agent** (picks a legal action, emits fake reasoning) so a full match runs
  end-to-end, deterministically, with events written to a log.
- Persist the full trajectory to SQLite.

**Exit criteria:** a match runs start→finish with dummy agents, produces a scored outcome, and
writes a complete trajectory. No LLM involved yet.

### Flagship environment spec — multi-issue negotiation

Two agents divide a fixed pool of items (e.g. 3 item types, quantities like [3 books, 2 hats, 1 ball]).
Each agent has **private per-item valuations** summing to the same total (so it's zero-sum-ish and
scorable). They alternate making **offers** (a proposed split) over up to N rounds. An agent may
**accept** the standing offer or **counter**. On acceptance, each agent scores its valuation of the
share it received. On no agreement by round N, both score 0 (or a small fallback). This is a
well-studied bargaining setup: clean payoffs, visible strategy, rich for comparing agent behavior.

Action schema: `{"type": "offer", "split": {...}}` | `{"type": "accept"}` | `{"type": "walk"}`.
Observation per agent: its own valuations, the item pool, full offer history, rounds remaining.
Public view (streamed): the offer history and whose turn it is — **never** the private valuations.

### Second environment spec — role-play scenarios (agent vs. agent)

Two agents play defined **roles** in an open-ended scenario, optionally seeded with **injected
context data**, and act it out turn by turn. Flagship scenario: **interviewer vs. interviewee**,
seeded with a job description (interviewer's context) and a CV (interviewee's context). Other
scenarios (negotiation-as-dialogue, support-agent vs. frustrated-customer, doctor vs. patient) drop
in as data + prompts, not new code.

This is the environment that proves the abstraction generalizes beyond objective-payoff games, and
it changes the scoring regime: there is **no natural payoff**, so it's scored entirely by a
**rubric-based LLM judge** over the finished transcript (Phase 4). That's a feature, not a gap — it
exercises the trajectory-judging capability that's the most eval-relevant thing here.

How it maps onto the existing interfaces (no new machinery):
- **Roles** = two agents with different `strategy_prompt`s (the role definition).
- **Injected data** = a per-role `context` field the environment folds into each agent's
  `observe()` — the JD for the interviewer, the CV for the candidate. Keep private context private
  (the candidate need not see the interviewer's private rubric/notes) and enforce that redaction at
  the env boundary, same as negotiation's valuations.
- **`step`** = append the agent's utterance to the shared transcript. The "action" is just
  `{"type": "say", "text": "…"}` plus any optional scenario fields (e.g. interviewer
  `{"type": "end_interview"}`).
- **`is_terminal`** = a turn/round cap, or a role-specific end signal (interviewer ends it).
- **`score`** = returns nothing objective; scoring is deferred to the Phase 4 judge rubric.
- **Public view** = the transcript so far (this one's naturally fully public — it's a conversation).

**Scope guard specific to role-play:** this is where scope creep lives, because "any two roles + any
data" is infinitely general. Do **not** build a generic scenario-authoring system for v1. Ship one or
two concrete, well-tuned scenarios (interview is the flagship — you have the domain context and the
CV/JD data model is trivial). A sharp interview role-play with a good judge rubric is a far better
demo than a shallow build-any-scenario framework. Generality is a claim you gesture at, not a system
you finish.

**Flagged follow-on (out of scope here, noted so it isn't lost): agent-vs-human.** Swap one role for
a live human and this becomes an interview *practice tool* — you answer a realistic AI interviewer
seeded with a real JD + your CV, and the judge scores *your* performance afterward. That's a
genuinely useful product (and one you'd use while job-hunting), but it's a different build:
human-in-the-loop turn-taking, live input UI, a participant rather than spectator experience. Ship
the agent-vs-agent watchable version first; spin the human version out as its own thing if it proves
compelling, where it can be a proper tool rather than one mode of an arena.

## Phase 2 — Backend: real LLM agents + live streaming

- Implement the **Claude-backed agent**: prompt = role + strategy + observation + action schema;
  stream the model's reasoning as `reasoning_delta` events; parse the trailing structured action,
  validate against the env schema, retry-once-then-forfeit on malformed (the same JSON-discipline
  pattern as any LLM-structured-output path).
- Wire the orchestrator to stream all events over the **single-writer WebSocket queue**.
- Handle **cancellation** cleanly: `cancel_match` must cancel any in-flight LLM call and close the
  stream without leaking tasks (async cancellation is a known footgun — test it explicitly).
- Handle agent/LLM errors as recoverable `error` events where possible, terminal where not.

**Exit criteria:** a real match between two Claude agents streams live reasoning + actions over the
socket, produces a valid scored outcome, persists the trajectory, and cancels cleanly mid-match.

## Phase 3 — Frontend: the live match view (the wow)

Built in parallel with Phases 1–2 against the frozen Phase 0 contract.

- A **match view**: each agent as a panel with its live-streaming reasoning ("thought" area filling
  in token by token), its latest action surfaced, and a visualization of the environment state (for
  negotiation: the item pool, the current proposed split, offer history; for role-play: the
  unfolding transcript as a conversation). A running **scoreboard** where the env is scored. The view
  should adapt to the environment's `public_view` shape rather than hard-code one game's layout.
- A **setup screen**: pick environment, configure each agent (label, model, strategy prompt), start.
- Connection handling: reconnect, and a clear terminal state on `match_ended` / `error`.
- Make it *glanceable and alive* — the streaming reasoning is the demo; lean into it visually.

**Exit criteria:** starting a match from the UI shows two agents thinking and acting live in real
time, the state visualization updates per action, and the final outcome renders. This is the
60-second demo.

## Phase 4 — Instrumentation & aggregation (the differentiator)

- **Match history** view: browse past matches, replay a trajectory turn-by-turn from persisted data.
- **Objective scoring** already exists for payoff games (env payoffs). Add a **rubric-based LLM
  judge** — optional for objective games (scoring extra dimensions like negotiation toughness,
  fairness, coherence), and the *sole* scorer for open-ended role-play (e.g. interview: interviewer
  probing quality, candidate answer strength, where it broke down). Per-environment rubric; judge
  runs as a separate pass so it never contaminates objective results. This is your LLM-as-judge
  wheelhouse and the capability most worth showing.
- **Aggregate/leaderboard** view: across many matches, win rates and mean payoffs **by strategy and
  by model** — the "which agent actually wins, and does a stronger model beat a cleverer prompt"
  question. This is the measurement layer that makes the project yours.
- **Reproducibility note (do this properly):** LLM nondeterminism means single matches prove
  nothing; aggregate claims need enough matches for signal, fixed valuations/seeds where possible,
  and controlled temperature. Surface match counts alongside win rates so the numbers are honest.
  This rigor is the thing that distinguishes your arena from a toy.

**Exit criteria:** you can run N matches of a matchup, see aggregate win rates by strategy/model with
match counts, and replay any individual trajectory.

## Phase 5 — Polish, second environment, deploy

- **Second environment: role-play (interviewer vs. interviewee)** — the agent-vs-agent open-ended
  scenario specced above, seeded with a JD + CV and scored by the rubric judge. This is the priority
  second environment: it proves the abstraction generalizes to open-ended, judge-only scenarios and
  showcases rubric-based trajectory scoring. (Judge-scored **debate** is an easy third if you want
  another, but role-play is the one that earns its place.)
- **Tournament mode:** run many matchups with **bounded concurrency** (`asyncio.Semaphore`) so you
  don't stampede the API rate limit — and this is where the concurrency competency shows.
- **Demo layer:** a README with a GIF/loom, a link to the (already-live, since Phase 0.5) Railway +
  Vercel deploy, and a short "what I found" writeup (the aggregate results). This is the portfolio
  door onto the work.

---

## Splitting the work across Claude Code + Codex

The Phase 0 contract is what makes parallel work safe — freeze it first, then:

- **One tool owns the backend track (Phases 1 → 2 → 4-backend):** environment, orchestrator, LLM
  agents, streaming, scoring, aggregation queries. This is the async/concurrency-heavy half.
- **The other owns the frontend track (Phase 3 → 4-frontend):** the live match view, setup, history
  replay, leaderboard. It codes against the frozen event schema + a mock WebSocket emitting canned
  events, so it doesn't block on the backend being live.
- They integrate once the backend streams real events. Because both built to the same frozen
  contract, integration is wiring, not rework.

Practical notes: keep the shared types (event schema, action schemas) in a single source of truth
each side generates from or mirrors, so a contract change is a deliberate, coordinated act — not a
silent drift that desyncs the two tracks. Do Phase 0 yourself (or with one tool) and review it
carefully; it's the cheapest place to spend care and the most expensive place to get wrong. Run each
phase as its own session, review the diff, integrate at the seams.

## Technical risks / scope guards

- **Stream serialization is the #1 backend risk** — parallel agent tasks writing one socket will
  interleave and tear the connection. Single writer draining a queue, from the start. Non-negotiable.
- **Async cancellation leaks** — stopping a match must cancel in-flight LLM calls and close streams
  without orphaning tasks. Test the cancel path explicitly; it's the classic footgun.
- **Malformed agent actions** — agents will emit invalid JSON/illegal moves. Validate against the env
  schema, retry once, forfeit the turn on repeat. Never let a bad action crash the match loop.
- **Cost** — a match is many LLM calls; a tournament is many matches. Cheap agent model, hard round
  caps, bounded tournament concurrency. Keep matches cheap enough to run hundreds for aggregate signal.
- **Private-info leakage** — the streamed `public_view` must never include agents' private valuations,
  or the whole game is void. Enforce the redaction at the env boundary, not the UI.
- **Reproducibility for aggregate claims** — control what you can (valuations, seeds, temperature),
  run enough matches, and always show N. Don't over-claim from a handful of nondeterministic runs.
- **Scope creep into the thesis** — resist making this rigorous enough to *be* the thesis. It's a
  sandbox and a portfolio piece; the research contribution lives in the separate thesis project.
- **No local dev environment** — this machine can't run the stack locally, so every change is
  verified against the live Railway/Vercel deploy from Phase 0.5 onward. This is why the deploy
  skeleton comes before feature work: cross-origin WSS, CORS, and SQLite-on-ephemeral-disk are the
  kinds of issues that otherwise surface for the first time under Phase 2's real streaming load, or
  worse, in Phase 5. Keep the Railway/Vercel deploy green continuously rather than batching changes
  and discovering integration breaks late.

The one to get right before anything else: the Phase 0 contract, because it's what lets two coding
agents build in parallel without colliding — freeze it, then let the tracks run.
