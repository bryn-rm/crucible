import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type {
  AgentConfig,
  AgentRosterEntry,
  ServerEvent,
  StartMatch,
} from '../contract/events';
import { LiveMatchSocket, type MatchSocket } from '../lib/ws';
import { listEnvironments } from '../lib/api';
import { actionLabel } from './actionLabel';
import { MatchState } from './MatchState';

type ConnectionState = 'connecting' | 'connected' | 'disconnected';

type AgentView = AgentRosterEntry & {
  reasoning: string;
  action?: Record<string, unknown>;
  active: boolean;
};

const MAX_RECONNECT_ATTEMPTS = 8;

const AgentCard = memo(function AgentCard({ agent, score }: { agent: AgentView; score?: number }) {
  const reasoningRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    const element = reasoningRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [agent.reasoning]);

  return (
    <article className={`agent-card ${agent.active ? 'active' : ''}`}>
      <header><div><span className="eyebrow">{agent.model}</span><h3>{agent.label}</h3></div><strong className="score">{score ?? '—'}</strong></header>
      <div className="reasoning"><span className="eyebrow">Live reasoning</span><p ref={reasoningRef}>{agent.reasoning || 'Waiting for this agent’s turn…'}{agent.active && <i className="cursor" />}</p></div>
      <div className="latest-action"><span className="eyebrow">Latest action</span><strong>{actionLabel(agent.action)}</strong></div>
    </article>
  );
});

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

export function MatchView() {
  const socketRef = useRef<MatchSocket | null>(null);
  const [connection, setConnection] = useState<ConnectionState>('connecting');
  const [configs, setConfigs] = useState(DEFAULT_AGENTS);
  const [environment, setEnvironment] = useState('negotiation');
  const [environments, setEnvironments] = useState<string[]>(['negotiation', 'role_play']);
  const [agents, setAgents] = useState<Record<string, AgentView>>({});
  const [matchId, setMatchId] = useState<string | null>(null);
  const [state, setState] = useState<Record<string, unknown> | null>(null);
  const [scores, setScores] = useState<Record<string, number>>({});
  const [status, setStatus] = useState('Ready for a new negotiation');
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const handleEvent = useCallback((event: ServerEvent) => {
    switch (event.type) {
      case 'match_started':
        setMatchId(event.match_id);
        setEnvironment(event.environment);
        setAgents(Object.fromEntries(event.agents.map((agent) => [agent.id, { ...agent, reasoning: '', active: false }])));
        setStatus(event.environment === 'role_play' ? 'Interview in progress' : 'Negotiation in progress');
        break;
      case 'turn_started':
        setAgents((current) => Object.fromEntries(Object.entries(current).map(([id, agent]) => [id, { ...agent, active: id === event.agent_id, reasoning: id === event.agent_id ? '' : agent.reasoning }])));
        setStatus(`Turn ${event.turn_no}`);
        break;
      case 'reasoning_delta':
        setAgents((current) => {
          const agent = current[event.agent_id];
          if (!agent) return current;
          return { ...current, [event.agent_id]: { ...agent, reasoning: agent.reasoning + event.chunk } };
        });
        break;
      case 'action':
        setAgents((current) => {
          const agent = current[event.agent_id];
          if (!agent) return current;
          return { ...current, [event.agent_id]: { ...agent, action: event.action, active: false } };
        });
        break;
      case 'state_update': setState(event.state); break;
      case 'score_update': setScores(event.scores); break;
      case 'match_ended':
        setScores(event.final_scores);
        setStatus(`${event.outcome} · ${event.reason.replace('_', ' ')}`);
        setRunning(false);
        setAgents((current) => Object.fromEntries(Object.entries(current).map(([id, agent]) => [id, { ...agent, active: false }])));
        break;
      case 'error':
        setError(event.message);
        if (!event.recoverable) setRunning(false);
        break;
    }
  }, []);

  useEffect(() => {
    let disposed = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let socket: MatchSocket;
    let attempts = 0;

    function connect() {
      setConnection('connecting');
      socket = new LiveMatchSocket();
      socketRef.current = socket;
      socket.onOpen(() => {
        attempts = 0;
        setConnection('connected');
        setError(null);
      });
      socket.onClose(() => {
        if (disposed) return;
        setConnection('disconnected');
        setRunning(false);
        attempts += 1;
        if (attempts > MAX_RECONNECT_ATTEMPTS) {
          setError('Could not reconnect to the arena. Check the backend and reload to try again.');
          return;
        }
        const delay = Math.min(1000 * 2 ** (attempts - 1), 30_000) + Math.random() * 500;
        setError(`Connection lost. Reconnecting (${attempts}/${MAX_RECONNECT_ATTEMPTS})…`);
        reconnectTimer = setTimeout(connect, delay);
      });
      socket.onError((socketError) => {
        if (!disposed) setError(socketError.message);
      });
      socket.onEvent(handleEvent);
    }

    connect();

    return () => {
      disposed = true;
      clearTimeout(reconnectTimer);
      socket.close();
    };
  }, [handleEvent]);

  useEffect(() => {
    const controller = new AbortController();
    listEnvironments(controller.signal)
      .then((items) => {
        if (items.length > 0) setEnvironments(items);
      })
      .catch((err: Error) => {
        if (err.name !== 'AbortError') setError(err.message);
      });
    return () => controller.abort();
  }, []);

  function updateConfig<K extends keyof AgentConfig>(index: number, field: K, value: AgentConfig[K]) {
    setConfigs((current) =>
      current.map((config, i) => (i === index ? { ...config, [field]: value } : config)),
    );
  }

  function startMatch() {
    const event: StartMatch = { type: 'start_match', environment, agents: configs };
    setAgents({});
    setState(null);
    setScores({});
    setError(null);
    setMatchId(null);
    setRunning(true);
    setStatus('Starting match…');
    if (!socketRef.current?.send(event)) {
      setRunning(false);
      setError('The arena connection is not open.');
    }
  }

  function cancelMatch() {
    if (connection === 'connected' && matchId) {
      socketRef.current?.send({ type: 'cancel_match', match_id: matchId });
    }
  }

  const resetMatch = useCallback(() => {
    setAgents({});
    setState(null);
    setScores({});
    setError(null);
    setMatchId(null);
    setRunning(false);
    setStatus('Ready for a new match');
  }, []);

  const roster = useMemo(() => Object.values(agents), [agents]);

  return (
    <main className="match-shell">
      <section className="hero-card">
        <div>
          <span className="eyebrow">Live experiment</span>
          <h2>Watch strategy become action.</h2>
          <p>Configure two agents, then follow every decision and response as it streams.</p>
        </div>
        <div className={`connection ${connection}`}><span />{connection}</div>
      </section>

      {error && <div className="error-banner">{error}</div>}

      {!running && roster.length === 0 && (
        <section className="setup-grid">
          <article className="setup-card">
            <span className="eyebrow">Environment</span>
            <label>Scenario
              <select value={environment} onChange={(e) => setEnvironment(e.target.value)}>
                {environments.map((name) => <option value={name} key={name}>{name.replace('_', ' ')}</option>)}
              </select>
            </label>
            <p className="empty-copy">
              {environment === 'role_play'
                ? 'Agent 1 interviews Agent 2. The completed transcript is scored separately by the rubric judge.'
                : 'Two agents bargain over a fixed item pool with private valuations.'}
            </p>
          </article>
          {configs.map((config, index) => (
            <article className="setup-card" key={config.id}>
              <span className="agent-number">0{index + 1}</span>
              <label>Agent label<input value={config.label} onChange={(e) => updateConfig(index, 'label', e.target.value)} /></label>
              <label>Model<input value={config.model} onChange={(e) => updateConfig(index, 'model', e.target.value)} /></label>
              <label>Strategy<textarea rows={4} value={config.strategy_prompt} onChange={(e) => updateConfig(index, 'strategy_prompt', e.target.value)} /></label>
              <label>Temperature<input type="number" min="0" max="2" step="0.1" value={config.temperature} onChange={(e) => updateConfig(index, 'temperature', Number(e.target.value))} /></label>
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
            {running ? <button className="cancel-button" onClick={cancelMatch} disabled={!matchId || connection !== 'connected'}>Cancel match</button> : <button className="new-button" onClick={resetMatch}>New match</button>}
          </section>
          <section className="agent-grid">
            {roster.map((agent) => (
              <AgentCard agent={agent} score={scores[agent.id]} key={agent.id} />
            ))}
          </section>
          <section className="environment-card"><header><div><span className="eyebrow">Public environment</span><h3>{environment === 'role_play' ? 'Interview transcript' : 'Negotiation table'}</h3></div>{state && typeof state.turns_taken === 'number' && typeof state.max_turns === 'number' && <span>{state.turns_taken} / {state.max_turns} turns</span>}</header><MatchState environment={environment} state={state} /></section>
        </>
      )}
    </main>
  );
}
