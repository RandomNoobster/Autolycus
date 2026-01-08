/**
 * API Client
 *
 * This module provides a configured fetch client for making API requests.
 * It handles token authentication and error handling.
 */

import type { ApiError } from '@/types';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

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

  const response = await fetch(url, {
    ...fetchOptions,
    headers: {
      'Content-Type': 'application/json',
      ...fetchOptions.headers,
    },
  });

  const data = await response.json();

  if (!response.ok) {
    const error: ApiError = {
      error: data.error || 'Request failed',
      message: data.message || 'An unexpected error occurred',
      code: data.code || 'UNKNOWN_ERROR',
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
