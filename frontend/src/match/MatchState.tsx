import { memo } from 'react';
import { actionLabel } from './actionLabel';

export const MatchState = memo(function MatchState({
  environment,
  state,
}: {
  environment: string;
  state: Record<string, unknown> | null;
}) {
  if (!state) {
    return <p className="empty-copy">The public match state will appear after the match starts.</p>;
  }

  if (environment === 'role_play') {
    const transcript = (state.transcript ?? []) as Array<{
      turn_no: number;
      agent_id: string;
      role: string;
      text: string;
    }>;
    return (
      <div className="history-list">
        {transcript.length === 0 && <p className="empty-copy">The interview is about to begin.</p>}
        {transcript.map((entry) => (
          <div className="history-row" key={entry.turn_no}>
            <span>{entry.role}</span>
            <strong>{entry.agent_id}</strong>
            <span>{entry.text}</span>
          </div>
        ))}
      </div>
    );
  }

  const items = (state.items ?? {}) as Record<string, number>;
  const history = (state.history ?? []) as Array<{
    turn_no: number;
    agent_id: string;
    action: Record<string, unknown>;
  }>;
  const standingOffer = state.standing_offer as
    | { agent_id: string; split: Record<string, number> }
    | null;

  return (
    <div className="state-content">
      <div className="item-pool">
        {Object.entries(items).map(([item, quantity]) => (
          <div className="item-chip" key={item}>
            <strong>{quantity}</strong>
            <span>{item}</span>
          </div>
        ))}
      </div>
      <div className="offer-card">
        <span className="eyebrow">Standing offer</span>
        <strong>
          {standingOffer
            ? `${standingOffer.agent_id} keeps ${Object.entries(standingOffer.split)
                .map(([item, quantity]) => `${quantity} ${item}`)
                .join(', ')}`
            : 'No offer yet'}
        </strong>
      </div>
      <div className="history-list">
        {history.map((entry) => (
          <div className="history-row" key={entry.turn_no}>
            <span>Turn {entry.turn_no}</span>
            <strong>{entry.agent_id}</strong>
            <span>{actionLabel(entry.action)}</span>
          </div>
        ))}
      </div>
    </div>
  );
});
