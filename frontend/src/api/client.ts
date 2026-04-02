/**
 * API Client
 *
 * This module provides a configured fetch client for making API requests.
 * It handles token authentication and error handling.
 */

import type { ApiError } from '@/types';

import { BACKEND_UNAVAILABLE_CODE } from './errors';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

const BACKEND_UNAVAILABLE_MESSAGE =
  'The Autolycus API is unreachable. Start the backend (or check VITE_API_URL and your dev proxy), then try again.';

function throwBackendUnavailable(detail?: string): never {
  const message = detail ? `${BACKEND_UNAVAILABLE_MESSAGE} (${detail})` : BACKEND_UNAVAILABLE_MESSAGE;
  const err: ApiError = {
    error: 'Cannot reach API',
    message,
    code: BACKEND_UNAVAILABLE_CODE,
  };
  throw err;
}

interface RequestOptions extends RequestInit {
  token?: string;
}

/**
 * Make an authenticated API request.
 *
 * @param endpoint - The API endpoint (e.g., '/api/raids')
 * @param options - Fetch options including optional token
 * @returns The JSON response data
 * @throws ApiError if the request fails
 */
export async function apiRequest<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const { token, ...fetchOptions } = options;

  // Build URL with token if provided
  let url = `${API_BASE_URL}${endpoint}`;
  if (token) {
    const separator = url.includes('?') ? '&' : '?';
    url = `${url}${separator}token=${encodeURIComponent(token)}`;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...fetchOptions,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...fetchOptions.headers,
      },
    });
  } catch (e) {
    const cause = e instanceof Error ? e.message : String(e);
    throwBackendUnavailable(cause);
  }

  const rawText = await response.text();
  let data: any = null;
  if (rawText) {
    try {
      data = JSON.parse(rawText);
    } catch {
      data = rawText;
    }
  }

  if (!response.ok) {
    const status = response.status;
    const gateway = status === 502 || status === 503 || status === 504;
    const emptyOrUnhelpful =
      data == null ||
      (typeof data === 'string' && (data.trim() === '' || !data.trim().startsWith('{')));

    if (gateway && emptyOrUnhelpful) {
      throwBackendUnavailable(`HTTP ${status}`);
    }

    const error: ApiError = {
      error: data?.error || (gateway ? 'Service unavailable' : 'Request failed'),
      message:
        data?.message ||
        (gateway
          ? 'The API server is not responding. It may be down or still starting.'
          : typeof data === 'string' && data.length < 400
            ? data
            : 'An unexpected error occurred'),
      code: data?.code || (gateway ? BACKEND_UNAVAILABLE_CODE : 'UNKNOWN_ERROR'),
    };
    throw error;
  }

  if (data === null || data === undefined || typeof data === 'string') {
    const error: ApiError = {
      error: 'Invalid response',
      message: typeof data === 'string' ? data : 'Response body was not JSON',
      code: 'INVALID_RESPONSE',
    };
    throw error;
  }

  return data as T;
}

/**
 * GET request helper
 */
export function apiGet<T>(endpoint: string, token?: string): Promise<T> {
  return apiRequest<T>(endpoint, { method: 'GET', token });
}

/**
 * POST request helper
 */
export function apiPost<T, B = unknown>(
  endpoint: string,
  body: B,
  token?: string
): Promise<T> {
  return apiRequest<T>(endpoint, {
    method: 'POST',
    body: JSON.stringify(body),
    token,
  });
}

/**
 * DELETE request helper
 */
export function apiDelete<T>(endpoint: string, token?: string): Promise<T> {
  return apiRequest<T>(endpoint, { method: 'DELETE', token });
}

/**
 * PUT request helper
 */
export function apiPut<T, B = unknown>(
  endpoint: string,
  body: B,
  token?: string
): Promise<T> {
  return apiRequest<T>(endpoint, {
    method: 'PUT',
    body: JSON.stringify(body),
    token,
  });
}
