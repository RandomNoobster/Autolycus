/**
 * Auth API Functions
 */

import { apiPost } from './client';

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
  return apiPost<TokenGenerateResponse, TokenGenerateRequest>(
    '/api/auth/token/generate',
    data
  );
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
