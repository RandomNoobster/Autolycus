/**
 * Auth API Functions (Discord OAuth session cookie)
 */

import { apiGet, apiPost } from './client';
import type {
  VerifyLinkRequest,
  VerifyLinkResponse,
  LinkedNationResponse,
} from '@/types';

export interface DiscordSessionResponse {
  authenticated: boolean;
  /** Discord snowflake. Above 2^53, so JSON parsing rounds it: don't use it as an id. */
  discord_user_id?: number;
  username?: string;
  global_name?: string;
  avatar?: string;
  avatar_url?: string;
  authenticated_at?: number;
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

export function unlinkDiscordNation(): Promise<{ success: boolean; removed?: boolean }> {
  return apiPost<{ success: boolean; removed?: boolean }, Record<string, never>>(
    '/api/auth/unlink-nation',
    {}
  );
}
