import { useState } from 'react';
import type { TournamentAgentConfig, TournamentResponse } from '../api/types';
import { getTournament, runTournament } from '../lib/api';

const DEFAULT_AGENTS: TournamentAgentConfig[] = [
  { id: 'agent-a', label: 'Atlas', model: 'scripted', strategy_prompt: 'Seek balanced agreements.', temperature: 0.7 },
  { id: 'agent-b', label: 'Nova', model: 'scripted', strategy_prompt: 'Open firmly and concede gradually.', temperature: 0.7 },
];

export function TournamentView() {
  const [agents, setAgents] = useState(DEFAULT_AGENTS);
  const [matches, setMatches] = useState(10);
  const [concurrency, setConcurrency] = useState(2);
  const [seed, setSeed] = useState(42);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<TournamentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  function updateAgent(index: number, field: keyof TournamentAgentConfig, value: string) {
    setAgents((current) => current.map((agent, i) => i === index ? { ...agent, [field]: value } : agent));
  }

  async function start() {
    setRunning(true);
    setResult(null);
    setError(null);
    try {
      let current = await runTournament({ environment: 'negotiation', agents, matches, concurrency, seed });
      setResult(current);
      while (current.status === 'running') {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        current = await getTournament(current.tournament_id);
        setResult(current);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Tournament failed');
    } finally {
      setRunning(false);
    }
  }

  return (
    <main className="match-shell">
      <section className="hero-card">
        <div>
          <span className="eyebrow">Batch experiment</span>
          <h2>Turn a matchup into evidence.</h2>
          <p>Run repeated negotiations with bounded concurrency. Every match is persisted and immediately feeds the leaderboard.</p>
        </div>
      </section>

      <section className="setup-grid">
        {agents.map((agent, index) => (
          <article className="setup-card" key={agent.id}>
            <span className="agent-number">0{index + 1}</span>
            <label>Agent label<input value={agent.label} onChange={(e) => updateAgent(index, 'label', e.target.value)} /></label>
            <label>Model<input value={agent.model} onChange={(e) => updateAgent(index, 'model', e.target.value)} /></label>
            <label>Strategy<textarea rows={3} value={agent.strategy_prompt} onChange={(e) => updateAgent(index, 'strategy_prompt', e.target.value)} /></label>
          </article>
        ))}
        <article className="setup-card tournament-settings">
          <label>Matches (1–50)<input type="number" min="1" max="50" value={matches} onChange={(e) => setMatches(Number(e.target.value))} /></label>
          <label>Concurrency (1–5)<input type="number" min="1" max="5" value={concurrency} onChange={(e) => setConcurrency(Number(e.target.value))} /></label>
          <label>Base seed<input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} /></label>
          <p className="empty-copy">Start with concurrency 1–2 for paid models, then raise it only within your provider rate limits.</p>
        </article>
        <button className="start-button" disabled={running || matches < 1 || matches > 50 || concurrency < 1 || concurrency > 5} onClick={start}>
          {running ? `Running ${matches} matches…` : 'Start tournament'}
        </button>
      </section>

      {error && <div className="error-banner">{error}</div>}
      {result && (
        <section className="environment-card">
          <header><div><span className="eyebrow">Tournament {result.status}</span><h3>{result.completed} / {result.requested} completed · {result.failed} failed</h3></div><span>Concurrency {result.concurrency}</span></header>
          <div className="history-list">
            {result.matches.map((match, index) => (
              <div className="history-row" key={match.match_id}>
                <span>Match {index + 1}</span>
                <strong>{match.status}</strong>
                <span>{match.error ?? match.outcome ?? match.reason}</span>
              </div>
            ))}
          </div>
          <p className="empty-copy tournament-note">Open Leaderboard to compare aggregate win rates, payoffs, and match counts.</p>
        </section>
      )}
    </main>
  );
}
