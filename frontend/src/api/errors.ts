/**
 * Normalized API / network errors for consistent UI handling.
 */

import type { ApiError } from '@/types';

export const BACKEND_UNAVAILABLE_CODE = 'BACKEND_UNAVAILABLE';

/**
 * What `apiRequest` throws. It is an `Error`, so `err instanceof Error ? err.message : …`
 * shows the server's message, and it carries the `ApiError` fields for code-based handling.
 */
export class ApiRequestError extends Error implements ApiError {
  readonly error: string;
  readonly code: string;
  /** HTTP status, or 0 when no response arrived. */
  readonly status: number;
  readonly retryAfterSeconds?: number;

  constructor({ error, message, code, status = 0, retryAfterSeconds }: ApiError) {
    super(message);
    this.name = 'ApiRequestError';
    this.error = error;
    this.code = code;
    this.status = status;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

/** True when the browser could not get an answer from the API (backend down, proxy error, network). */
export function isBackendUnreachableError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  const e = error as Partial<ApiError> & { name?: string };
  // Errors from apiRequest are classified where the response was read; their message is
  // server text that may happen to say "failed to fetch".
  if (typeof e.code === 'string') return e.code === BACKEND_UNAVAILABLE_CODE;
  const msg = String(e.message || '');
  if (/failed to fetch|networkerror|load failed|network request failed|fetch.*aborted/i.test(msg)) {
    return true;
  }
  return e.name === 'TypeError' && /fetch/i.test(msg);
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiRequestError) return error;
  if (error && typeof error === 'object' && 'code' in error && 'message' in error) {
    const e = error as ApiError;
    if (typeof e.message === 'string' && typeof e.code === 'string') {
      return {
        error: typeof e.error === 'string' ? e.error : 'Error',
        message: e.message,
        code: e.code,
        ...(typeof e.status === 'number' ? { status: e.status } : {}),
        ...(typeof e.retryAfterSeconds === 'number' ? { retryAfterSeconds: e.retryAfterSeconds } : {}),
      };
    }
  }
  if (error instanceof Error) {
    return {
      error: 'Error',
      message: error.message || 'Something went wrong',
      code: isBackendUnreachableError(error) ? BACKEND_UNAVAILABLE_CODE : 'UNKNOWN_ERROR',
    };
  }
  return {
    error: 'Error',
    message: 'An unexpected error occurred',
    code: 'UNKNOWN_ERROR',
  };
}

/** Worth one retry: no answer from the API, or a 5xx. Never a 4xx, which won't change on retry. */
export function isTransientApiError(error: unknown): boolean {
  if (isBackendUnreachableError(error)) return true;
  const status = (error as Partial<ApiError> | null)?.status;
  return typeof status === 'number' && status >= 500;
}
