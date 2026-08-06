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

export type MatchEndedReason = 'agreement' | 'round_limit' | 'error' | 'cancelled';

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
