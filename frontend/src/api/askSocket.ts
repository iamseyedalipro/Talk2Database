/**
 * Ask over WebSocket: streams step-by-step progress while the AI works.
 *
 * Fallback contract: `askViaSocket` resolves once the server confirms the run
 * started (`run_started`). Any failure BEFORE that — constructor throw, socket
 * error/close, bad first response, or a start timeout — rejects the promise so
 * the caller can retry over plain HTTP without double-spending AI tokens.
 * After `run_started`, failures are delivered to `onEvent` as an `error`
 * event and the caller must NOT re-run the question.
 */

import type { AskPayload, AskProgressEvent } from './types';

export interface AskSocketHandlers {
  /** Every server event after (and including) `run_started`, in order. */
  onEvent: (event: AskProgressEvent) => void;
}

export interface AskSocketHandle {
  /** Ask the server to cancel the run (it answers with a `cancelled` event). */
  cancel: () => void;
}

const START_TIMEOUT_MS = 5000;

function socketUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}/api/ask/ws`;
}

export function askViaSocket(
  payload: AskPayload,
  token: string,
  handlers: AskSocketHandlers,
): Promise<AskSocketHandle> {
  return new Promise((resolve, reject) => {
    let socket: WebSocket;
    try {
      socket = new WebSocket(socketUrl());
    } catch (err) {
      reject(err instanceof Error ? err : new Error('WebSocket unavailable'));
      return;
    }

    let started = false;
    let settled = false;
    let finished = false;

    const fail = (message: string) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      try {
        socket.close();
      } catch {
        /* already closed */
      }
      reject(new Error(message));
    };

    const timer = window.setTimeout(() => fail('Timed out waiting for the ask to start.'), START_TIMEOUT_MS);

    socket.onopen = () => {
      socket.send(
        JSON.stringify({
          type: 'start',
          token,
          connection_id: payload.connection_id,
          question: payload.question,
        }),
      );
    };

    socket.onerror = () => {
      if (!started) fail('WebSocket connection failed.');
    };

    socket.onclose = () => {
      if (!started) {
        fail('WebSocket closed before the ask started.');
      } else if (!finished) {
        // Server went away mid-run: report it, never silently re-run.
        finished = true;
        handlers.onEvent({
          type: 'error',
          seq: Number.MAX_SAFE_INTEGER,
          code: 'connection_lost',
          detail: 'The connection was lost while the AI was working. Please ask again.',
        });
      }
    };

    socket.onmessage = (msg: MessageEvent<string>) => {
      let event: AskProgressEvent;
      try {
        event = JSON.parse(msg.data) as AskProgressEvent;
      } catch {
        return;
      }

      if (!started) {
        if (event.type === 'run_started') {
          started = true;
          settled = true;
          window.clearTimeout(timer);
          resolve({
            cancel: () => {
              try {
                socket.send(JSON.stringify({ type: 'cancel' }));
              } catch {
                /* socket already gone; the server run dies with it */
              }
            },
          });
        } else {
          // An error (bad token, bad request) before the run began.
          fail(event.type === 'error' ? event.detail : 'Unexpected server response.');
          return;
        }
      }

      if (finished) return;
      handlers.onEvent(event);

      if (event.type === 'final_result' || event.type === 'error' || event.type === 'cancelled') {
        finished = true;
        try {
          socket.close();
        } catch {
          /* already closed */
        }
      }
    };
  });
}
