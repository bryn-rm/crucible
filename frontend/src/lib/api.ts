/**
 * REST client for match history, replay, and the leaderboard (Phase 4).
 *
 * Mirrors lib/ws.ts's VITE_WS_URL pattern: an explicit env var in
 * deployment (frontend and backend are different origins on Vercel/Railway),
 * falling back to same-origin `/api` for local/dev setups that proxy it.
 */

import type { JudgeResult, LeaderboardResponse, MatchDetail, MatchSummary, TournamentRequest, TournamentResponse } from '../api/types';

const API_BASE_URL = import.meta.env.VITE_API_URL ?? `${location.origin}/api`;

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(`${response.status} ${response.statusText}${body ? `: ${body}` : ''}`);
  }
  return response.json() as Promise<T>;
}

export function listMatches(limit = 20, offset = 0): Promise<MatchSummary[]> {
  return apiFetch(`/matches?limit=${limit}&offset=${offset}`);
}

export function getMatch(matchId: string): Promise<MatchDetail> {
  return apiFetch(`/matches/${matchId}`);
}

export function getLeaderboard(): Promise<LeaderboardResponse> {
  return apiFetch('/leaderboard');
}

export function runJudge(matchId: string): Promise<JudgeResult> {
  return apiFetch(`/matches/${matchId}/judge`, { method: 'POST' });
}

export function runTournament(request: TournamentRequest): Promise<TournamentResponse> {
  return apiFetch('/tournaments', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
}

export function getTournament(tournamentId: string): Promise<TournamentResponse> {
  return apiFetch(`/tournaments/${tournamentId}`);
}
