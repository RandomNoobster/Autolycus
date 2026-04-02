/**
 * Raids API Functions
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

/**
 * Fetch raid targets data.
 *
 * @param token - The authentication token from the URL
 * @returns RaidsResponse with targets and alerts
 */
export interface RaidFilterParams {
  attackerNationId?: number;
  targetNationIds?: number[] | string;
  useSavedTargets?: boolean;
  minCities?: number;
  maxCities?: number;
  alliance?: string;
  beige?: boolean;
  maxWars?: number;
  inactiveMinDays?: number;
  scope?: 'all' | 'apps_or_none' | 'no_alliance';
  minBeigeLoot?: number;
  performance?: boolean;
  minScore?: number;
  maxScore?: number;
  vmode?: boolean; // When true: only VM; when false: exclude VM; omitted: backend default
}

export function fetchRaids(
  filters: RaidFilterParams = {}
): Promise<RaidsResponse> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value === undefined || value === null) return;
    if (Array.isArray(value)) {
      params.set(key, value.join(','));
      return;
    }
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

/**
 * Add a beige reminder for a nation.
 *
 * @param token - The authentication token
 * @param data - The reminder request data
 * @returns Confirmation response
 */
export function addReminder(
  data: ReminderRequest
): Promise<ReminderResponse> {
  return apiPost<ReminderResponse, ReminderRequest>('/api/raids/reminders', data);
}

/**
 * Remove a beige reminder for a nation.
 *
 * @param token - The authentication token
 * @param nationId - The nation ID to remove reminder for
 * @returns Confirmation response
 */
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

/**
 * Alliance search result type.
 */
export interface AllianceSearchResult {
  value: string;
  label: string;
  id: string;
  acronym: string;
}

/**
 * Search for alliances by name, acronym, or ID (fuzzy matching).
 *
 * @param token - The authentication token
 * @param query - The search query string
 * @param limit - Maximum number of results (default: 10)
 * @returns Array of matching alliances
 */
export function searchAlliances(
  query: string,
  limit: number = 10
): Promise<AllianceSearchResult[]> {
  const params = new URLSearchParams();
  params.set('q', query);
  params.set('limit', String(limit));
  return apiGet<AllianceSearchResult[]>(`/api/raids/alliances/search?${params.toString()}`);
}
