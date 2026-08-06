/**
 * Match WebSocket client.
 *
 * Thin wrapper so the match view is written against a small interface
 * (connect, send, onEvent, close) rather than the raw WebSocket API. This is
 * what makes `MockMatchSocket` swappable in during frontend-first dev,
 * before the backend streams real events (Phase 3 builds in parallel with
 * Phases 1-2 against the frozen contract).
 */

import type { ClientEvent, ServerEvent } from '../contract/events';

export interface MatchSocket {
  send(event: ClientEvent): void;
  onEvent(handler: (event: ServerEvent) => void): () => void;
  close(): void;
}

export class LiveMatchSocket implements MatchSocket {
  private ws: WebSocket;
  private handlers = new Set<(event: ServerEvent) => void>();

  constructor(url: string = `${location.origin.replace(/^http/, 'ws')}/ws/match`) {
    this.ws = new WebSocket(url);
    this.ws.onmessage = (msg) => {
      const event = JSON.parse(msg.data) as ServerEvent;
      this.handlers.forEach((h) => h(event));
    };
  }

  send(event: ClientEvent): void {
    this.ws.send(JSON.stringify(event));
  }

  onEvent(handler: (event: ServerEvent) => void): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  close(): void {
    this.ws.close();
  }
}

/**
 * Replays a canned event sequence on a timer, shaped exactly like the real
 * contract. Lets the match view be built and demoed before the backend
 * exists. Swap for LiveMatchSocket once the backend streams real matches.
 */
export class MockMatchSocket implements MatchSocket {
  private handlers = new Set<(event: ServerEvent) => void>();
  private timers: ReturnType<typeof setTimeout>[] = [];
  private script: ServerEvent[];
  private stepMs: number;

  constructor(script: ServerEvent[] = [], stepMs = 300) {
    this.script = script;
    this.stepMs = stepMs;
  }

  send(_event: ClientEvent): void {
    this.script.forEach((event, i) => {
      const t = setTimeout(() => this.handlers.forEach((h) => h(event)), i * this.stepMs);
      this.timers.push(t);
    });
  }

  onEvent(handler: (event: ServerEvent) => void): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  close(): void {
    this.timers.forEach(clearTimeout);
    this.timers = [];
  }
}
