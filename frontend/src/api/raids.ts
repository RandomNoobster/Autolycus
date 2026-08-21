/**
 * Raids API Functions
 *
 * GET /api/raids/ accepts score bounds, optional attackerNationId, and vmode only.
 * Alliance, beige, wars, inactivity, and similar filters are applied client-side on the raids page.
 */

import { apiGet, apiPost, apiDelete, apiPut } from './client';
import type {
  RaidsResponse,
  ReminderRequest,
  ReminderResponse,
  RemindersResponse,
  ReminderConfigRequest,
  ReminderConfigResponse,
} from '@/types';

/** Query params supported by GET /api/raids/ */
export interface RaidFilterParams {
  attackerNationId?: number;
  minScore?: number;
  maxScore?: number;
  /** When false (default), exclude vacation-mode nations */
  vmode?: boolean;
}

/** Fetch raid targets from the cached nations database. */
export function fetchRaids(
  filters: RaidFilterParams = {}
): Promise<RaidsResponse> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value === undefined || value === null) return;
    if (typeof value === 'boolean') {
      params.set(key, value ? 'true' : 'false');
    } else {
      params.set(key, String(value));
    }
  });
  const qs = params.toString();
  const endpoint = qs ? `/api/raids/?${qs}` : '/api/raids/';
  return apiGet<RaidsResponse>(endpoint);
}

/** Nation score for war-range autofill (live PnW, with SQLite fallback). */
export interface LiveNationScore {
  id: number;
  nationName: string;
  leaderName: string;
  score: number;
  /** `live` from PnW API, `cache` from nations.db */
  source?: 'live' | 'cache';
  fetchedAt: string;
}

export function fetchLiveNationScore(nationId: number): Promise<LiveNationScore> {
  return apiGet<LiveNationScore>(`/api/raids/nation/${nationId}/live`);
}

/** Add a beige/VM exit reminder for a nation (requires Discord session). */
export function addReminder(
  data: ReminderRequest
): Promise<ReminderResponse> {
  return apiPost<ReminderResponse, ReminderRequest>('/api/raids/reminders', data);
}

/** Remove a beige/VM exit reminder for a nation (requires Discord session). */
export function removeReminder(
  nationId: number
): Promise<ReminderResponse> {
  return apiDelete<ReminderResponse>(`/api/raids/reminders/${nationId}`);
}

export function fetchReminders(): Promise<RemindersResponse> {
  return apiGet<RemindersResponse>('/api/raids/reminders');
}

export function updateReminderConfig(
  data: ReminderConfigRequest
): Promise<ReminderConfigResponse> {
  return apiPut<ReminderConfigResponse, ReminderConfigRequest>('/api/raids/reminders/config', data);
}

export interface AllianceSearchResult {
  value: string;
  label: string;
  id: string;
  acronym: string;
}

/** Search alliances by name, acronym, or ID (fuzzy match). */
export function searchAlliances(
  query: string,
  limit: number = 10
): Promise<AllianceSearchResult[]> {
  const params = new URLSearchParams();
  params.set('q', query);
  params.set('limit', String(limit));
  return apiGet<AllianceSearchResult[]>(`/api/raids/alliances/search?${params.toString()}`);
}
