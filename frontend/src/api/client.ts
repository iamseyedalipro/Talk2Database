/**
 * Typed `fetch` wrapper for the Talk2Database API.
 *
 * - Prefixes every request with the `/api` base path.
 * - Injects the bearer token returned by `getToken()`.
 * - Throws a typed {@link ApiError} carrying `{ status, detail }`.
 * - On any 401 it invokes the registered unauthorized handler (logout).
 */

const BASE_URL = '/api';

/** Error thrown for any non-2xx API response. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

type TokenGetter = () => string | null;
type UnauthorizedHandler = () => void;

let getToken: TokenGetter = () => null;
let onUnauthorized: UnauthorizedHandler = () => undefined;

/** Wire the client to the auth store. Called once during app bootstrap. */
export function configureClient(options: {
  getToken: TokenGetter;
  onUnauthorized: UnauthorizedHandler;
}): void {
  getToken = options.getToken;
  onUnauthorized = options.onUnauthorized;
}

function authHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  const token = getToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  return headers;
}

/** Best-effort extraction of the server's `detail` field from an error body. */
async function extractDetail(res: Response): Promise<string> {
  try {
    const data: unknown = await res.clone().json();
    if (data && typeof data === 'object' && 'detail' in data) {
      const { detail } = data as { detail: unknown };
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail)) {
        // FastAPI validation errors come back as a list of objects.
        return detail
          .map((d) =>
            d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : String(d),
          )
          .join('; ');
      }
      if (detail != null) return String(detail);
    }
  } catch {
    // fall through to status text
  }
  return res.statusText || `Request failed with status ${res.status}`;
}

async function handle<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    onUnauthorized();
    throw new ApiError(401, await extractDetail(res));
  }
  if (!res.ok) {
    throw new ApiError(res.status, await extractDetail(res));
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, init);
  return handle<T>(res);
}

export const api = {
  get<T>(path: string): Promise<T> {
    return request<T>(path, { method: 'GET', headers: authHeaders() });
  },

  post<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  },

  patch<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, {
      method: 'PATCH',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  },

  del<T>(path: string): Promise<T> {
    return request<T>(path, { method: 'DELETE', headers: authHeaders() });
  },

  /** Multipart upload (e.g. SQL dumps). Does NOT set Content-Type so the
   * browser can add the multipart boundary itself. */
  postForm<T>(path: string, form: FormData): Promise<T> {
    return request<T>(path, {
      method: 'POST',
      headers: authHeaders(),
      body: form,
    });
  },

  /**
   * POST that returns a binary attachment (CSV export). Resolves with the
   * downloaded blob and the server-suggested filename (falling back to
   * `fallbackName`).
   */
  async download(
    path: string,
    body: unknown,
    fallbackName: string,
  ): Promise<{ blob: Blob; filename: string }> {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
    });
    if (res.status === 401) {
      onUnauthorized();
      throw new ApiError(401, await extractDetail(res));
    }
    if (!res.ok) {
      throw new ApiError(res.status, await extractDetail(res));
    }
    const blob = await res.blob();
    const filename = filenameFromDisposition(res.headers.get('content-disposition'), fallbackName);
    return { blob, filename };
  },
};

/** Parse `Content-Disposition` for a filename, tolerating `filename*` form. */
export function filenameFromDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const star = /filename\*=(?:UTF-8'')?["']?([^"';]+)["']?/i.exec(header);
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1]);
    } catch {
      return star[1];
    }
  }
  const plain = /filename=["']?([^"';]+)["']?/i.exec(header);
  return plain?.[1] ?? fallback;
}

/** Trigger a browser download for a blob. */
export function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
