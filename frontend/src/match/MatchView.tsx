import { useEffect, useRef, useState } from 'react';
import type {
  AgentConfig,
  AgentRosterEntry,
  ServerEvent,
  StartMatch,
} from '../contract/events';
import { LiveMatchSocket, type MatchSocket } from '../lib/ws';

type ConnectionState = 'connecting' | 'connected' | 'disconnected';

type AgentView = AgentRosterEntry & {
  reasoning: string;
  action?: Record<string, unknown>;
  active: boolean;
};

const DEFAULT_AGENTS: AgentConfig[] = [
  {
    id: 'agent-a',
    label: 'Atlas',
    model: 'scripted',
    strategy_prompt: 'Seek a balanced agreement without giving away high-value items.',
    temperature: 0.7,
  },
  {
    id: 'agent-b',
    label: 'Nova',
    model: 'scripted',
    strategy_prompt: 'Start firmly, then make measured concessions to reach agreement.',
    temperature: 0.7,
  },
];

export function actionLabel(action?: Record<string, unknown>) {
  if (!action) return 'Waiting for an action';
  if (action.type === 'offer') {
    const split = action.split as Record<string, number> | undefined;
    return `Offers to keep ${Object.entries(split ?? {})
      .map(([item, quantity]) => `${quantity} ${item}`)
      .join(', ')}`;
  }
  return String(action.type ?? 'Unknown action');
}

export function MatchState({ state }: { state: Record<string, unknown> | null }) {
  if (!state) {
    return <p className="empty-copy">The public match state will appear after the match starts.</p>;
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
}

export function MatchView() {
  const socketRef = useRef<MatchSocket | null>(null);
  const [connection, setConnection] = useState<ConnectionState>('connecting');
  const [configs, setConfigs] = useState(DEFAULT_AGENTS);
  const [agents, setAgents] = useState<Record<string, AgentView>>({});
  const [matchId, setMatchId] = useState<string | null>(null);
  const [state, setState] = useState<Record<string, unknown> | null>(null);
  const [scores, setScores] = useState<Record<string, number>>({});
  const [status, setStatus] = useState('Ready for a new negotiation');
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    let disposed = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let socket: MatchSocket;

    function connect() {
      setConnection('connecting');
      socket = new LiveMatchSocket();
      socketRef.current = socket;
      socket.onOpen(() => {
        setConnection('connected');
        setError(null);
      });
      socket.onClose(() => {
        if (disposed) return;
        setConnection('disconnected');
        setRunning(false);
        setError('Connection lost. Reconnecting…');
        reconnectTimer = setTimeout(connect, 2000);
      });
      socket.onError(() => setError('The arena connection failed.'));
      socket.onEvent(handleEvent);
    }

    connect();

    return () => {
      disposed = true;
      clearTimeout(reconnectTimer);
      socket.close();
    };
  }, []);

  function handleEvent(event: ServerEvent) {
    switch (event.type) {
      case 'match_started':
        setMatchId(event.match_id);
        setAgents(
          Object.fromEntries(
            event.agents.map((agent) => [
              agent.id,
              { ...agent, reasoning: '', active: false },
            ]),
          ),
        );
        setStatus('Negotiation in progress');
        break;
      case 'turn_started':
        setAgents((current) =>
          Object.fromEntries(
            Object.entries(current).map(([id, agent]) => [
              id,
              { ...agent, active: id === event.agent_id, reasoning: id === event.agent_id ? '' : agent.reasoning },
            ]),
          ),
        );
        setStatus(`Turn ${event.turn_no}`);
        break;
      case 'reasoning_delta':
        setAgents((current) => ({
          ...current,
          [event.agent_id]: {
            ...current[event.agent_id],
            reasoning: `${current[event.agent_id]?.reasoning ?? ''}${event.chunk}`,
          },
        }));
        break;
      case 'action':
        setAgents((current) => ({
          ...current,
          [event.agent_id]: { ...current[event.agent_id], action: event.action, active: false },
        }));
        break;
      case 'state_update':
        setState(event.state);
        break;
      case 'score_update':
        setScores(event.scores);
        break;
      case 'match_ended':
        setScores(event.final_scores);
        setStatus(`${event.outcome} · ${event.reason.replace('_', ' ')}`);
        setRunning(false);
        setAgents((current) =>
          Object.fromEntries(Object.entries(current).map(([id, agent]) => [id, { ...agent, active: false }])),
        );
        break;
      case 'error':
        setError(event.message);
        if (!event.recoverable) setRunning(false);
        break;
    }
  }

  function updateConfig(index: number, field: keyof AgentConfig, value: string | number) {
    setConfigs((current) =>
      current.map((config, i) => (i === index ? { ...config, [field]: value } : config)),
    );
  }

  function startMatch() {
    const event: StartMatch = { type: 'start_match', environment: 'negotiation', agents: configs };
    setAgents({});
    setState(null);
    setScores({});
    setError(null);
    setMatchId(null);
    setRunning(true);
    setStatus('Starting match…');
    socketRef.current?.send(event);
  }

  function cancelMatch() {
    if (matchId) socketRef.current?.send({ type: 'cancel_match', match_id: matchId });
  }

  const roster = Object.values(agents);

  return (
    <main className="match-shell">
      <section className="hero-card">
        <div>
          <span className="eyebrow">Live experiment</span>
          <h2>Watch strategy become action.</h2>
          <p>Configure two agents, then follow every offer and concession as it streams.</p>
        </div>
        <div className={`connection ${connection}`}><span />{connection}</div>
      </section>

      {!running && roster.length === 0 && (
        <section className="setup-grid">
          {configs.map((config, index) => (
            <article className="setup-card" key={config.id}>
              <span className="agent-number">0{index + 1}</span>
              <label>Agent label<input value={config.label} onChange={(e) => updateConfig(index, 'label', e.target.value)} /></label>
              <label>Model<input value={config.model} onChange={(e) => updateConfig(index, 'model', e.target.value)} /></label>
              <label>Strategy<textarea rows={4} value={config.strategy_prompt} onChange={(e) => updateConfig(index, 'strategy_prompt', e.target.value)} /></label>
            </article>
          ))}
          <button className="start-button" disabled={connection !== 'connected'} onClick={startMatch}>
            {connection === 'connected' ? 'Start live match' : 'Connecting to arena…'}
          </button>
        </section>
      )}

      {(running || roster.length > 0) && (
        <>
          <section className="match-toolbar">
            <div><span className="eyebrow">Match status</span><strong>{status}</strong></div>
            {running ? <button className="cancel-button" onClick={cancelMatch} disabled={!matchId}>Cancel match</button> : <button className="new-button" onClick={() => setAgents({})}>New match</button>}
          </section>
          {error && <div className="error-banner">{error}</div>}
          <section className="agent-grid">
            {roster.map((agent) => (
              <article className={`agent-card ${agent.active ? 'active' : ''}`} key={agent.id}>
                <header><div><span className="eyebrow">{agent.model}</span><h3>{agent.label}</h3></div><strong className="score">{scores[agent.id] ?? '—'}</strong></header>
                <div className="reasoning"><span className="eyebrow">Live reasoning</span><p>{agent.reasoning || 'Waiting for this agent’s turn…'}{agent.active && <i className="cursor" />}</p></div>
                <div className="latest-action"><span className="eyebrow">Latest action</span><strong>{actionLabel(agent.action)}</strong></div>
              </article>
            ))}
          </section>
          <section className="environment-card"><header><div><span className="eyebrow">Public environment</span><h3>Negotiation table</h3></div>{state && <span>{String(state.turns_taken)} / {String(state.max_turns)} turns</span>}</header><MatchState state={state} /></section>
        </>
      )}
    </main>
  );
}
