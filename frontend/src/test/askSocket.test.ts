import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { askViaSocket } from '../api/askSocket';
import type { AskProgressEvent } from '../api/types';

/** Scripted stand-in for the browser WebSocket. */
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  sent: string[] = [];
  closed = false;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((msg: { data: string }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.closed = true;
  }

  // -- test helpers --
  open() {
    this.onopen?.();
  }

  emit(event: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(event) });
  }
}

const payload = { connection_id: 7, question: 'total?' };

function latestSocket(): FakeWebSocket {
  const socket = FakeWebSocket.instances[0];
  if (!socket) throw new Error('no WebSocket was constructed');
  return socket;
}

describe('askViaSocket', () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal('WebSocket', FakeWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('sends start on open and resolves on run_started', async () => {
    const events: AskProgressEvent[] = [];
    const promise = askViaSocket(payload, 'jwt', { onEvent: (e) => events.push(e) });
    const socket = latestSocket();
    socket.open();

    expect(JSON.parse(socket.sent[0] ?? '{}')).toEqual({
      type: 'start',
      token: 'jwt',
      connection_id: 7,
      question: 'total?',
    });

    socket.emit({ type: 'run_started', seq: 1, mode: 'standard', provider: 'p', model: 'm' });
    const handle = await promise;
    expect(events[0]?.type).toBe('run_started');

    socket.emit({ type: 'status', seq: 2, stage: 'schema', message: 'reading' });
    expect(events).toHaveLength(2);

    handle.cancel();
    expect(JSON.parse(socket.sent[1] ?? '{}')).toEqual({ type: 'cancel' });
  });

  it('rejects when the socket errors before the run starts (HTTP fallback)', async () => {
    const promise = askViaSocket(payload, 'jwt', { onEvent: vi.fn() });
    const socket = latestSocket();
    socket.onerror?.();
    await expect(promise).rejects.toThrow(/connection failed/i);
    expect(socket.closed).toBe(true);
  });

  it('rejects on a pre-start error event with the server detail', async () => {
    const promise = askViaSocket(payload, 'bad', { onEvent: vi.fn() });
    const socket = latestSocket();
    socket.open();
    socket.emit({ type: 'error', seq: 1, code: 'unauthorized', detail: 'Not authenticated' });
    await expect(promise).rejects.toThrow('Not authenticated');
  });

  it('rejects on the start timeout', async () => {
    vi.useFakeTimers();
    const promise = askViaSocket(payload, 'jwt', { onEvent: vi.fn() });
    const rejection = expect(promise).rejects.toThrow(/timed out/i);
    vi.advanceTimersByTime(6000);
    await rejection;
  });

  it('reports a connection lost error (not a rejection) after the run started', async () => {
    const events: AskProgressEvent[] = [];
    const promise = askViaSocket(payload, 'jwt', { onEvent: (e) => events.push(e) });
    const socket = latestSocket();
    socket.open();
    socket.emit({ type: 'run_started', seq: 1, mode: 'standard', provider: 'p', model: 'm' });
    await promise;

    socket.onclose?.();
    const last = events[events.length - 1];
    expect(last?.type).toBe('error');
    expect(last && 'code' in last ? last.code : null).toBe('connection_lost');
  });

  it('stops delivering events after a terminal event', async () => {
    const events: AskProgressEvent[] = [];
    const promise = askViaSocket(payload, 'jwt', { onEvent: (e) => events.push(e) });
    const socket = latestSocket();
    socket.open();
    socket.emit({ type: 'run_started', seq: 1, mode: 'standard', provider: 'p', model: 'm' });
    await promise;

    socket.emit({ type: 'cancelled', seq: 2 });
    socket.emit({ type: 'status', seq: 3, stage: 'x', message: 'late' });
    expect(events.map((e) => e.type)).toEqual(['run_started', 'cancelled']);
    expect(socket.closed).toBe(true);
  });
});
