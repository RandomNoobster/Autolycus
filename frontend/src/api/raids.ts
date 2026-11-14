/**
 * Raids API Functions
 *
 * GET /api/raids/ accepts score bounds, optional attackerNationId, and vmode only.
 * Alliance, beige, wars, inactivity, and similar filters are applied client-side on the raids page.
 */

import { apiGet, apiPost, apiDelete, apiPut, withQuery } from './client';
import type {
  RaidsResponse,
  ReminderRequest,
  ReminderResponse,
  RemindersResponse,
  ReminderConfigRequest,
  ReminderConfigResponse,
  ReminderChannelsRequest,
  ReminderChannelsResponse,
  ReminderDeliveryResponse,
  TestDmResponse,
} from '@/types';

/** Query params supported by GET /api/raids/ */
export type RaidFilterParams = {
  attackerNationId?: number;
  minScore?: number;
  maxScore?: number;
  /** When false (default), exclude vacation-mode nations */
  vmode?: boolean;
};

/** Fetch raid targets from the cached nations database. */
export function fetchRaids(
  filters: RaidFilterParams = {},
  signal?: AbortSignal
): Promise<RaidsResponse> {
  return apiGet<RaidsResponse>(withQuery('/api/raids/', filters), signal);
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

/** Delivery status only (channels, DM status, push devices, recent problems). Light enough to poll. */
export function fetchReminderDelivery(): Promise<ReminderDeliveryResponse> {
  return apiGet<ReminderDeliveryResponse>('/api/raids/reminders/delivery');
}

/**
 * Queue a test DM (202). Returns the in-flight test if one is already queued.
 * 429 RATE_LIMITED (1 per minute, 10 per day) with a Retry-After header.
 */
export function requestTestDm(): Promise<TestDmResponse> {
  return apiPost<TestDmResponse, Record<string, never>>('/api/raids/reminders/test-dm', {});
}

/**
 * Switch delivery channels. 400 CHANNEL_REQUIRED (both off), 409 NO_PUSH_DEVICES,
 * 503 PUSH_NOT_CONFIGURED.
 */
export function updateReminderChannels(
  channels: ReminderChannelsRequest
): Promise<ReminderChannelsResponse> {
  return apiPut<ReminderChannelsResponse, ReminderChannelsRequest>('/api/raids/reminders/channels', channels);
}
