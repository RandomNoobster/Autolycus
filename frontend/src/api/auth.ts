/**
 * Auth API Functions
 */

import { apiGet, apiPost } from './client';
import type {
  VerifyLinkRequest,
  VerifyLinkResponse,
  LinkedNationResponse,
} from '@/types';

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

export interface DiscordSessionResponse {
  authenticated: boolean;
  discord_user_id?: number;
  username?: string;
  global_name?: string;
  avatar?: string;
  avatar_url?: string;
  authenticated_at?: number;
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

export function getDiscordSession(): Promise<DiscordSessionResponse> {
  return apiGet<DiscordSessionResponse>('/api/auth/me');
}

export function logoutDiscordSession(): Promise<{ success: boolean; message: string }> {
  return apiPost<{ success: boolean; message: string }, Record<string, never>>(
    '/api/auth/logout',
    {}
  );
}

export function getDiscordLoginUrl(redirectPath: string = '/raids'): string {
  return `/api/auth/discord/start?redirect=${encodeURIComponent(redirectPath)}`;
}

export function verifyDiscordLink(data: VerifyLinkRequest): Promise<VerifyLinkResponse> {
  return apiPost<VerifyLinkResponse, VerifyLinkRequest>('/api/auth/verify', data);
}

export function getLinkedNation(): Promise<LinkedNationResponse> {
  return apiGet<LinkedNationResponse>('/api/auth/linked-nation');
}
