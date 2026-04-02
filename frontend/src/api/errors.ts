/**
 * Normalized API / network errors for consistent UI handling.
 */

import type { ApiError } from '@/types';

export const BACKEND_UNAVAILABLE_CODE = 'BACKEND_UNAVAILABLE';

/** True when the browser could not complete the request (backend down, CORS, DNS, etc.). */
export function isBackendUnreachableError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  const e = error as Partial<ApiError> & { name?: string };
  if (e.code === BACKEND_UNAVAILABLE_CODE) return true;
  if (e.code === 'NETWORK_ERROR') return true;
  const msg = String(e.message || '').toLowerCase();
  if (
    /failed to fetch|networkerror|load failed|network request failed|fetch.*aborted/i.test(msg)
  ) {
    return true;
  }
  if (e.name === 'TypeError' && /fetch/i.test(String(e.message || ''))) return true;
  return false;
}

export function toApiError(error: unknown): ApiError {
  if (error && typeof error === 'object' && 'code' in error && 'message' in error) {
    const e = error as ApiError;
    if (typeof e.message === 'string' && typeof e.code === 'string') {
      return {
        error: typeof e.error === 'string' ? e.error : 'Error',
        message: e.message,
        code: e.code,
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
