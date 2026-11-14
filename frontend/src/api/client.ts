/**
 * API Client
 *
 * A fetch wrapper for the Autolycus API. It sends the session cookie and turns every
 * failure into an `ApiRequestError`.
 */

import type { ApiError } from '@/types';

import { ApiRequestError, BACKEND_UNAVAILABLE_CODE } from './errors';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

const BACKEND_UNAVAILABLE_MESSAGE = import.meta.env.DEV
  ? 'The Autolycus API is unreachable. Start the backend (or check VITE_API_URL and your dev proxy), then try again.'
  : "Can't reach the Autolycus server right now. Please try again in a minute.";

function backendUnavailable(detail: string, status = 0): ApiRequestError {
  return new ApiRequestError({
    error: 'Cannot reach API',
    message: `${BACKEND_UNAVAILABLE_MESSAGE} (${detail})`,
    code: BACKEND_UNAVAILABLE_CODE,
    status,
  });
}

function isAbortError(e: unknown): boolean {
  return typeof e === 'object' && e !== null && (e as { name?: unknown }).name === 'AbortError';
}

/** Parse a `Retry-After` header (delay in seconds, or an HTTP date) into whole seconds. */
function parseRetryAfter(value: string | null): number | undefined {
  const trimmed = value?.trim();
  if (!trimmed) return undefined;
  if (/^\d+$/.test(trimmed)) return Number(trimmed);
  const retryAtMs = Date.parse(trimmed);
  if (Number.isNaN(retryAtMs)) return undefined;
  return Math.max(0, Math.ceil((retryAtMs - Date.now()) / 1000));
}

type QueryValue = string | number | boolean | null | undefined;

/** `path?key=value&…`, skipping null, undefined and non-finite numbers. */
export function withQuery(path: string, params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    if (typeof value === 'number' && !Number.isFinite(value)) continue;
    search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `${path}?${qs}` : path;
}

/**
 * Make an API request.
 *
 * @param endpoint - The API endpoint (e.g., '/api/raids/')
 * @param options - Fetch options (method, body, signal, ...)
 * @returns The JSON response data
 * @throws ApiRequestError if the request fails
 */
export async function apiRequest<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  let rawText: string;
  try {
    response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      credentials: 'include',
      headers: {
        ...(options.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    });
    rawText = await response.text();
  } catch (e) {
    // A cancelled query is not an outage; let the caller see the abort.
    if (isAbortError(e)) throw e;
    throw backendUnavailable(e instanceof Error ? e.message : String(e));
  }

  let data: unknown = null;
  if (rawText) {
    try {
      data = JSON.parse(rawText);
    } catch {
      data = rawText;
    }
  }
  const body: Partial<ApiError> =
    data !== null && typeof data === 'object' ? (data as Partial<ApiError>) : {};

  if (!response.ok) {
    const status = response.status;
    // The API answers every error with a JSON object. A 5xx without one came from a proxy
    // in front of it (nginx, Cloudflare, the Vite dev proxy) that couldn't reach it.
    if (status >= 500 && !body.code && !body.message) {
      throw backendUnavailable(`HTTP ${status}`, status);
    }
    const retryAfterSeconds = parseRetryAfter(response.headers.get('Retry-After'));
    throw new ApiRequestError({
      error: body.error || 'Request failed',
      message:
        body.message ||
        (typeof data === 'string' && data.length < 400 ? data : 'An unexpected error occurred'),
      code: body.code || (status >= 500 ? BACKEND_UNAVAILABLE_CODE : 'UNKNOWN_ERROR'),
      status,
      retryAfterSeconds,
    });
  }

  if (data === null || typeof data !== 'object') {
    throw new ApiRequestError({
      error: 'Invalid response',
      message: 'The server sent a response the app could not read.',
      code: 'INVALID_RESPONSE',
      status: response.status,
    });
  }

  return data as T;
}

/**
 * GET request helper
 */
export function apiGet<T>(endpoint: string, signal?: AbortSignal): Promise<T> {
  return apiRequest<T>(endpoint, { method: 'GET', signal });
}

/**
 * POST request helper
 */
export function apiPost<T, B = unknown>(endpoint: string, body: B): Promise<T> {
  return apiRequest<T>(endpoint, { method: 'POST', body: JSON.stringify(body) });
}

/**
 * DELETE request helper
 */
export function apiDelete<T>(endpoint: string): Promise<T> {
  return apiRequest<T>(endpoint, { method: 'DELETE' });
}

/**
 * PUT request helper
 */
export function apiPut<T, B = unknown>(endpoint: string, body: B): Promise<T> {
  return apiRequest<T>(endpoint, { method: 'PUT', body: JSON.stringify(body) });
}
