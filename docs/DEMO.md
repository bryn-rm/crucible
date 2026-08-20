# 60-second demo capture

Use this after the Railway backend and Vercel frontend pass every check in
[`DEPLOYMENT.md`](../DEPLOYMENT.md). Record the browser at the production Vercel URL; Loom, Screen
Studio, OBS, or any GIF recorder is suitable.

## Before recording

- Use two fast, enabled model IDs and confirm both provider keys are configured.
- Pre-run a small tournament so Replay and Leaderboard contain meaningful data.
- Keep browser developer tools and all API keys off screen.
- Use a desktop viewport around 1440×900 and reload before recording.

## Shot list

| Time | Action | Point demonstrated |
| --- | --- | --- |
| 0–8s | Show the Match setup and start a negotiation. | Models and strategies are experiment variables. |
| 8–28s | Let both reasoning panels stream and an offer land. | Live multi-agent orchestration and the single-writer event stream. |
| 28–38s | Show the final allocation and scores. | Objective environment scoring. |
| 38–48s | Open Replay and step between two turns. | Full persisted trajectories. |
| 48–56s | Open Leaderboard. | Aggregate results with match counts. |
| 56–60s | Flash Tournament and the role-play selector. | Bounded batch execution and pluggable environments. |

## Publish checklist

- [ ] Upload the recording or optimized GIF.
- [ ] Add its public URL/embed near the top of `README.md`.
- [ ] Replace `<your-vercel-domain>` in the README with the production frontend URL.
- [ ] Add the public Railway `/health` URL for operational verification, not as the user-facing app.
- [ ] Update [`RESULTS.md`](RESULTS.md) with the first controlled LLM comparison.
