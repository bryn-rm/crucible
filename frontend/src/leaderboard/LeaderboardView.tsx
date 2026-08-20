/**
 * Aggregate leaderboard (Phase 4): win rates and mean payoffs by strategy
 * and by model, with honest match counts alongside every claim — a handful
 * of nondeterministic LLM matches proves nothing on its own.
 */

import { useEffect, useState } from 'react';
import type { LeaderboardEntry, LeaderboardResponse } from '../api/types';
import { getLeaderboard } from '../lib/api';

function LeaderboardTable({ title, entries }: { title: string; entries: LeaderboardEntry[] }) {
  if (entries.length === 0) {
    return (
      <div className="environment-card">
        <header>
          <div>
            <span className="eyebrow">{title}</span>
            <h3>No completed matches yet</h3>
          </div>
        </header>
      </div>
    );
  }

  return (
    <div className="environment-card">
      <header>
        <div>
          <span className="eyebrow">{title}</span>
          <h3>Win rate &amp; mean payoff</h3>
        </div>
      </header>
      <div style={{ overflowX: 'auto' }}>
        <table className="leaderboard-table">
          <thead>
            <tr>
              <th>Key</th>
              <th>Matches</th>
              <th>Wins</th>
              <th>Draws</th>
              <th>Win rate</th>
              <th>Mean payoff</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.key}>
                <td>{entry.key}</td>
                <td>{entry.matches}</td>
                <td>{entry.wins}</td>
                <td>{entry.draws}</td>
                <td>{(entry.win_rate * 100).toFixed(0)}%</td>
                <td>{entry.mean_payoff.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function LeaderboardView() {
  const [data, setData] = useState<LeaderboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getLeaderboard()
      .then(setData)
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <main className="match-shell">
      <section className="hero-card">
        <div>
          <span className="eyebrow">Instrumentation</span>
          <h2>Which agent actually wins?</h2>
          <p>Aggregated across every completed negotiation, grouped by model and by strategy prompt.</p>
        </div>
      </section>

      {error && <div className="error-banner">{error}</div>}

      {data && (
        <section className="leaderboard-tables">
          <LeaderboardTable title="By model" entries={data.by_model} />
          <LeaderboardTable title="By strategy" entries={data.by_strategy} />
        </section>
      )}
    </main>
  );
}
