/**
 * Server -> client WebSocket event schema.
 *
 * TypeScript mirror of backend/app/contract/events.py. This is the frozen
 * contract (see docs/multi_agent_arena_build_plan.md, Phase 0). Do not change
 * a field's meaning or remove a field without a coordinated update to the
 * Python source in the same change.
 */

export interface AgentRosterEntry {
  id: string;
  label: string;
  model: string;
  strategy: string;
}

export interface MatchStarted {
  type: 'match_started';
  match_id: string;
  environment: string;
  agents: AgentRosterEntry[];
}

export interface TurnStarted {
  type: 'turn_started';
  match_id: string;
  agent_id: string;
  turn_no: number;
}

export interface ReasoningDelta {
  type: 'reasoning_delta';
  match_id: string;
  agent_id: string;
  turn_no: number;
  chunk: string;
}

export interface ActionEvent {
  type: 'action';
  match_id: string;
  agent_id: string;
  turn_no: number;
  action: Record<string, unknown>;
}

export interface StateUpdate {
  type: 'state_update';
  match_id: string;
  state: Record<string, unknown>;
}

export interface ScoreUpdate {
  type: 'score_update';
  match_id: string;
  scores: Record<string, number>;
}

export type MatchEndedReason = 'agreement' | 'completed' | 'round_limit' | 'error' | 'cancelled';

export interface MatchEnded {
  type: 'match_ended';
  match_id: string;
  outcome: string;
  final_scores: Record<string, number>;
  reason: MatchEndedReason;
}

export interface ErrorEvent {
  type: 'error';
  match_id?: string | null;
  recoverable: boolean;
  message: string;
}

export type ServerEvent =
  | MatchStarted
  | TurnStarted
  | ReasoningDelta
  | ActionEvent
  | StateUpdate
  | ScoreUpdate
  | MatchEnded
  | ErrorEvent;

// --- Client -> server ---

export interface AgentConfig {
  id: string;
  label: string;
  model: string;
  strategy_prompt: string;
  temperature: number;
}

export interface StartMatch {
  type: 'start_match';
  environment: string;
  agents: AgentConfig[];
}

export interface CancelMatch {
  type: 'cancel_match';
  match_id: string;
}

export type ClientEvent = StartMatch | CancelMatch;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasString(value: Record<string, unknown>, key: string): boolean {
  return typeof value[key] === 'string';
}

function hasNumber(value: Record<string, unknown>, key: string): boolean {
  return typeof value[key] === 'number' && Number.isFinite(value[key]);
}

function isNumberRecord(value: unknown): value is Record<string, number> {
  return isRecord(value) && Object.values(value).every((item) => typeof item === 'number');
}

/** Validate the hand-mirrored server contract at its network boundary. */
export function parseServerEvent(value: unknown): ServerEvent {
  if (!isRecord(value) || typeof value.type !== 'string') {
    throw new Error('server event must be an object with a string type');
  }

  const matchId = () => {
    if (!hasString(value, 'match_id')) throw new Error(`${value.type} is missing match_id`);
  };
  switch (value.type) {
    case 'match_started':
      matchId();
      if (!hasString(value, 'environment') || !Array.isArray(value.agents)) {
        throw new Error('invalid match_started event');
      }
      for (const agent of value.agents) {
        if (!isRecord(agent) || !['id', 'label', 'model', 'strategy'].every((key) => hasString(agent, key))) {
          throw new Error('invalid match_started agent');
        }
      }
      break;
    case 'turn_started':
      matchId();
      if (!hasString(value, 'agent_id') || !hasNumber(value, 'turn_no')) throw new Error('invalid turn_started event');
      break;
    case 'reasoning_delta':
      matchId();
      if (!hasString(value, 'agent_id') || !hasNumber(value, 'turn_no') || !hasString(value, 'chunk')) {
        throw new Error('invalid reasoning_delta event');
      }
      break;
    case 'action':
      matchId();
      if (!hasString(value, 'agent_id') || !hasNumber(value, 'turn_no') || !isRecord(value.action)) {
        throw new Error('invalid action event');
      }
      break;
    case 'state_update':
      matchId();
      if (!isRecord(value.state)) throw new Error('invalid state_update event');
      break;
    case 'score_update':
      matchId();
      if (!isNumberRecord(value.scores)) throw new Error('invalid score_update event');
      break;
    case 'match_ended':
      matchId();
      if (
        !hasString(value, 'outcome') ||
        !isNumberRecord(value.final_scores) ||
        !['agreement', 'completed', 'round_limit', 'error', 'cancelled'].includes(String(value.reason))
      ) throw new Error('invalid match_ended event');
      break;
    case 'error':
      if (typeof value.recoverable !== 'boolean' || !hasString(value, 'message')) throw new Error('invalid error event');
      if (value.match_id != null && typeof value.match_id !== 'string') throw new Error('invalid error match_id');
      break;
    default:
      throw new Error(`unknown server event type: ${value.type}`);
  }
  return value as unknown as ServerEvent;
}
