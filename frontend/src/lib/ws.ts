/**
 * Match WebSocket client.
 *
 * Thin wrapper so the match view is written against a small interface
 * (connect, send, onEvent, close) rather than the raw WebSocket API. This is
 * what makes `MockMatchSocket` swappable in during frontend-first dev,
 * before the backend streams real events (Phase 3 builds in parallel with
 * Phases 1-2 against the frozen contract).
 */

import { parseServerEvent, type ClientEvent, type ServerEvent } from '../contract/events';

export interface MatchSocket {
  send(event: ClientEvent): boolean;
  onEvent(handler: (event: ServerEvent) => void): () => void;
  onOpen(handler: () => void): () => void;
  onClose(handler: () => void): () => void;
  onError(handler: (error: Error) => void): () => void;
  close(): void;
}

export class LiveMatchSocket implements MatchSocket {
  private ws: WebSocket;
  private handlers = new Set<(event: ServerEvent) => void>();
  private openHandlers = new Set<() => void>();
  private closeHandlers = new Set<() => void>();
  private errorHandlers = new Set<(error: Error) => void>();

  constructor(
    url: string = import.meta.env.VITE_WS_URL ||
      `${location.origin.replace(/^http/, 'ws')}/ws/match`,
  ) {
    const authenticatedUrl = new URL(url);
    const token = sessionStorage.getItem('arena_api_token');
    if (token) authenticatedUrl.searchParams.set('token', token);
    this.ws = new WebSocket(authenticatedUrl);
    this.ws.onopen = () => this.openHandlers.forEach((handler) => handler());
    this.ws.onclose = () => this.closeHandlers.forEach((handler) => handler());
    this.ws.onerror = () => this.reportError(new Error('WebSocket connection error'));
    this.ws.onmessage = (msg) => {
      try {
        const event = parseServerEvent(JSON.parse(String(msg.data)));
        this.handlers.forEach((handler) => handler(event));
      } catch (error) {
        this.reportError(error instanceof Error ? error : new Error('Invalid WebSocket frame'));
      }
    };
  }

  private reportError(error: Error): void {
    this.errorHandlers.forEach((handler) => handler(error));
  }

  send(event: ClientEvent): boolean {
    if (this.ws.readyState !== WebSocket.OPEN) {
      this.reportError(new Error('The arena connection is not open.'));
      return false;
    }
    this.ws.send(JSON.stringify(event));
    return true;
  }

  onEvent(handler: (event: ServerEvent) => void): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  onOpen(handler: () => void): () => void {
    this.openHandlers.add(handler);
    if (this.ws.readyState === WebSocket.OPEN) queueMicrotask(handler);
    return () => this.openHandlers.delete(handler);
  }

  onClose(handler: () => void): () => void {
    this.closeHandlers.add(handler);
    return () => this.closeHandlers.delete(handler);
  }

  onError(handler: (error: Error) => void): () => void {
    this.errorHandlers.add(handler);
    return () => this.errorHandlers.delete(handler);
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

  send(_event: ClientEvent): boolean {
    this.timers.forEach(clearTimeout);
    this.timers = [];
    this.script.forEach((event, i) => {
      const t = setTimeout(() => this.handlers.forEach((h) => h(event)), i * this.stepMs);
      this.timers.push(t);
    });
    return true;
  }

  onEvent(handler: (event: ServerEvent) => void): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  onOpen(handler: () => void): () => void {
    queueMicrotask(handler);
    return () => undefined;
  }

  onClose(_handler: () => void): () => void {
    return () => undefined;
  }

  onError(_handler: (error: Error) => void): () => void {
    return () => undefined;
  }

  close(): void {
    this.timers.forEach(clearTimeout);
    this.timers = [];
  }
}
