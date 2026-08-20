/**
 * REST response DTOs (Phase 4). Hand mirror of backend/app/api/schemas.py.
 * Ordinary REST types, not part of the frozen WS contract in src/contract/.
 */

export interface MatchAgentOut {
  agent_id: string;
  label: string;
  model: string;
  strategy: string;
  final_score: number | null;
}

export interface MatchSummary {
  id: string;
  environment: string;
  status: string;
  created_at: string;
  ended_at: string | null;
  outcome: string | null;
  reason: string | null;
  agents: MatchAgentOut[];
}

export interface TurnOut {
  turn_no: number;
  agent_id: string;
  reasoning_text: string;
  action_json: Record<string, unknown>;
  state_after_json: Record<string, unknown>;
  latency_ms: number | null;
}

export interface ScoreOut {
  agent_id: string;
  dimension: string;
  value: number;
}

export interface MatchDetail extends MatchSummary {
  turns: TurnOut[];
  scores: ScoreOut[];
}

export interface LeaderboardEntry {
  key: string;
  matches: number;
  wins: number;
  draws: number;
  win_rate: number;
  mean_payoff: number;
}

export interface LeaderboardResponse {
  by_model: LeaderboardEntry[];
  by_strategy: LeaderboardEntry[];
}

export interface AgentJudgment {
  scores: Record<string, number>;
  rationale: string;
}

export interface JudgeResult {
  dimensions: string[];
  agents: Record<string, AgentJudgment>;
}

export interface TournamentAgentConfig {
  id: string;
  label: string;
  model: string;
  strategy_prompt: string;
  temperature: number;
}

export interface TournamentRequest {
  environment: string;
  agents: TournamentAgentConfig[];
  matches: number;
  concurrency: number;
  seed: number;
}

export interface TournamentMatchResult {
  match_id: string;
  status: string;
  outcome: string | null;
  reason: string | null;
  final_scores: Record<string, number>;
  error: string | null;
}

export interface TournamentResponse {
  tournament_id: string;
  status: string;
  requested: number;
  completed: number;
  failed: number;
  concurrency: number;
  matches: TournamentMatchResult[];
}
