/**
 * Auth API Functions
 */

import { apiPost, apiRequest } from './client';

interface TokenGenerateRequest {
  user_id?: string | number;
  data_type: 'raids' | 'builds' | 'damage';
  expires_in?: number;
}

interface TokenGenerateResponse {
  token: string;
  expires_at: number;
  data_type: string;
  message: string;
}

interface TokenVerifyRequest {
  token: string;
}

interface TokenVerifyResponse {
  valid: boolean;
  payload?: any;
  error?: string;
  code?: string;
  message?: string;
}

/**
 * Generate a secure access token for a specific data type.
 *
 * @param data - Token generation request data
 * @returns Token response with token string and expiration
 */
export function generateToken(
  data: TokenGenerateRequest
): Promise<TokenGenerateResponse> {
  const authKey = import.meta.env.VITE_AUTH_TOKEN_API_KEY as string | undefined;

  if (authKey) {
    return apiRequest<TokenGenerateResponse>('/api/auth/token/generate', {
      method: 'POST',
      body: JSON.stringify(data),
      headers: {
        'X-Auth-Token': authKey,
      },
    });
  }

  return apiPost<TokenGenerateResponse, TokenGenerateRequest>('/api/auth/token/generate', data);
}

/**
 * Verify if a token is valid.
 *
 * @param token - The token to verify
 * @returns Verification response
 */
export function verifyToken(token: string): Promise<TokenVerifyResponse> {
  return apiPost<TokenVerifyResponse, TokenVerifyRequest>(
    '/api/auth/token/verify',
    { token }
  );
}
