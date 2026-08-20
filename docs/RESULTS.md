# Arena results

## Scripted tournament baseline

This baseline verifies the Phase 5 tournament pipeline; it does **not** compare model intelligence.

| Setting | Value |
| --- | --- |
| Environment | Multi-issue negotiation |
| Matches | 10 |
| Base seed | 42 |
| Concurrency | 2 |
| Seat policy | Agent order alternated; each adjacent pair shared a valuation seed |
| Failed matches | 0 |

| Agent | Wins | Win rate | Mean payoff |
| --- | ---: | ---: | ---: |
| Balanced scripted baseline | 5 | 50% | 48.8 |
| Firm scripted baseline | 5 | 50% | 48.8 |

### What this establishes

- The bounded runner completes and persists a multi-match batch.
- Alternating seats removes the deterministic first-mover advantage visible when agent order is fixed.
- Repeated matches feed the existing model/strategy leaderboard with honest match counts.

### What this does not establish

Both entries used the same scripted fallback behavior; their strategy labels do not alter that code.
The equal result therefore validates the control setup, not the relative quality of the prompts.

## Production experiment to run

After provider keys are configured, run at least 20 paired matches per comparison with a fixed base
seed, alternating seats, and a controlled temperature. Compare one variable at a time:

1. Same model, different strategy prompt.
2. Different model, same strategy prompt.
3. Repeat at a second seed range before making a portfolio claim.

Record model IDs, temperature, base seed, match count, failures, wins/draws, mean payoff, and judge
dimensions. Treat any conclusion as provisional until it repeats across seed ranges.
