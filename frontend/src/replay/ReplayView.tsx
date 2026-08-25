/**
 * Trajectory replay (Phase 4): browse persisted matches and step through a
 * chosen match's turns one at a time from the data app/orchestrator.py wrote
 * during the live match.
 */

import { useEffect, useRef, useState } from 'react';
import type { MatchDetail, MatchSummary } from '../api/types';
import { getMatch, listMatches, runJudge } from '../lib/api';
import { actionLabel } from '../match/actionLabel';
import { MatchState } from '../match/MatchState';

function formatTime(iso: string) {
  return new Date(iso).toLocaleString();
}

function MatchList({
  matches,
  selectedId,
  onSelect,
}: {
  matches: MatchSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (matches.length === 0) {
    return <p className="empty-copy">No matches yet — run one from the Match tab first.</p>;
  }

  return (
    <div className="match-list">
      {matches.map((match) => (
        <button
          key={match.id}
          className={`match-list-item ${match.id === selectedId ? 'active' : ''}`}
          onClick={() => onSelect(match.id)}
        >
          <div>
            <strong>{match.environment}</strong>
            <span className="eyebrow">{formatTime(match.created_at)}</span>
          </div>
          <div className="match-list-agents">
            {match.agents.map((agent) => (
              <span key={agent.agent_id}>
                {agent.label} · {agent.final_score ?? '—'}
              </span>
            ))}
          </div>
          <span className={`match-status ${match.status}`}>{match.status}</span>
        </button>
      ))}
    </div>
  );
}

export function ReplayView() {
  const judgeRequestRef = useRef<AbortController | null>(null);
  const [matches, setMatches] = useState<MatchSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<MatchDetail | null>(null);
  const [turnIndex, setTurnIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [judging, setJudging] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    listMatches(20, 0, controller.signal)
      .then((value) => {
        setMatches(value);
        setError(null);
      })
      .catch((err: Error) => {
        if (err.name !== 'AbortError') setError(err.message);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => () => judgeRequestRef.current?.abort(), []);

  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    setDetail(null);
    setTurnIndex(0);
    setError(null);
    getMatch(selectedId, controller.signal)
      .then((value) => {
        setDetail(value);
        setError(null);
      })
      .catch((err: Error) => {
        if (err.name !== 'AbortError') setError(err.message);
      });
    return () => controller.abort();
  }, [selectedId]);

  const turn = detail?.turns[turnIndex];

  async function judgeSelectedMatch() {
    if (!detail) return;
    judgeRequestRef.current?.abort();
    const controller = new AbortController();
    judgeRequestRef.current = controller;
    setJudging(true);
    setError(null);
    try {
      await runJudge(detail.id, controller.signal);
      setDetail(await getMatch(detail.id, controller.signal));
      setError(null);
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : 'Judge request failed');
      }
    } finally {
      if (judgeRequestRef.current === controller) {
        judgeRequestRef.current = null;
        setJudging(false);
      }
    }
  }

  return (
    <main className="match-shell">
      <section className="hero-card">
        <div>
          <span className="eyebrow">Trajectory replay</span>
          <h2>Step through a finished match.</h2>
          <p>Every turn is exactly what was persisted live — reasoning, action, and the state after it.</p>
        </div>
      </section>

      {error && <div className="error-banner">{error}</div>}

      <section className="replay-layout">
        <MatchList matches={matches} selectedId={selectedId} onSelect={setSelectedId} />

        {detail && turn && (
          <div className="replay-detail">
            <section className="match-toolbar">
              <div>
                <span className="eyebrow">
                  Turn {turn.turn_no} of {detail.turns.length}
                </span>
                <strong>{detail.outcome ?? detail.status}</strong>
              </div>
              <div className="replay-controls">
                {detail.status === 'completed' && (
                  <button disabled={judging} onClick={judgeSelectedMatch}>
                    {judging ? 'Judging…' : 'Run judge'}
                  </button>
                )}
                <button
                  disabled={turnIndex === 0}
                  onClick={() => setTurnIndex((i) => Math.max(0, i - 1))}
                >
                  ← Prev
                </button>
                <button
                  disabled={turnIndex >= detail.turns.length - 1}
                  onClick={() => setTurnIndex((i) => Math.min(detail.turns.length - 1, i + 1))}
                >
                  Next →
                </button>
              </div>
            </section>

            <section className="agent-grid">
              <article className="agent-card">
                <header>
                  <div>
                    <span className="eyebrow">{turn.agent_id}</span>
                    <h3>Turn {turn.turn_no}</h3>
                  </div>
                  {turn.latency_ms != null && <strong className="score">{turn.latency_ms}ms</strong>}
                </header>
                <div className="reasoning">
                  <span className="eyebrow">Reasoning</span>
                  <p>{turn.reasoning_text || '(no reasoning recorded)'}</p>
                </div>
                <div className="latest-action">
                  <span className="eyebrow">Action</span>
                  <strong>{actionLabel(turn.action_json)}</strong>
                </div>
              </article>

              <article className="environment-card">
                <header>
                  <div>
                    <span className="eyebrow">Public state after this turn</span>
                    <h3>{detail.environment}</h3>
                  </div>
                </header>
                <MatchState environment={detail.environment} state={turn.state_after_json} />
              </article>
            </section>

            {detail.scores.length > 0 && (
              <section className="environment-card">
                <header>
                  <div>
                    <span className="eyebrow">Final scores</span>
                    <h3>By dimension</h3>
                  </div>
                </header>
                <div className="history-list">
                  {detail.scores.map((score, i) => (
                    <div className="history-row" key={i}>
                      <span>{score.dimension}</span>
                      <strong>{score.agent_id}</strong>
                      <span>{score.value}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
