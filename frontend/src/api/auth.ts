/**
 * Auth API Functions
 */

import { apiPost } from './client';

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

interface TokenExchangeRequest {
  code: string;
}

/**
 * Exchange a bot-issued authorization code for a signed access token.
 *
 * @param data - Token exchange request data
 * @returns Token response with token string and expiration
 */
export function exchangeToken(
  data: TokenExchangeRequest
): Promise<TokenGenerateResponse> {
  return apiPost<TokenGenerateResponse, TokenExchangeRequest>('/api/auth/token/exchange', data);
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
