import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api, configureClient, filenameFromDisposition } from '../api/client';

describe('api client', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockReset();
    configureClient({ getToken: () => 'tok-123', onUnauthorized: () => undefined });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('attaches the bearer token and base path on GET', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await api.get('/system/status');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/system/status');
    const headers = new Headers(init.headers);
    expect(headers.get('Authorization')).toBe('Bearer tok-123');
  });

  it('serializes JSON bodies and sets Content-Type on POST', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    await api.post('/ask', { question: 'hello' });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe('POST');
    expect(init.body).toBe(JSON.stringify({ question: 'hello' }));
    const headers = new Headers(init.headers);
    expect(headers.get('Content-Type')).toBe('application/json');
  });

  it('throws a typed ApiError carrying the server detail', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'no data imported yet' }), {
        status: 409,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await expect(api.post('/ask', { question: 'x' })).rejects.toMatchObject({
      status: 409,
      detail: 'no data imported yet',
    });
  });

  it('invokes the unauthorized handler on 401', async () => {
    const onUnauthorized = vi.fn();
    configureClient({ getToken: () => null, onUnauthorized });
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'expired' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await expect(api.get('/auth/me')).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it('parses filenames from Content-Disposition headers', () => {
    expect(filenameFromDisposition('attachment; filename="report.csv"', 'fallback.csv')).toBe(
      'report.csv',
    );
    expect(filenameFromDisposition(null, 'fallback.csv')).toBe('fallback.csv');
  });
});
