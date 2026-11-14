/**
 * Reminder delivery status (channels, Discord DM status, push devices, recent problems).
 */

import { useQuery } from '@tanstack/react-query';

import { fetchReminderDelivery } from '@/api';
import { deliveryPollInterval, REMINDER_DELIVERY_QUERY_KEY } from '@/lib/reminderDelivery';
import type { ApiError, ReminderDelivery } from '@/types';

export interface UseReminderDeliveryOptions {
  /** Only fetch when signed in with Discord. Default true. */
  enabled?: boolean;
  /** Poll while a test DM is on its way. Default true; the sidebar turns it off. */
  poll?: boolean;
  /**
   * When to refresh on tab focus. Default 'always'. The always-mounted sidebar uses
   * 'whenNeedsAttention', so it only re-checks while it shows its warning.
   */
  focusRefresh?: 'always' | 'whenNeedsAttention';
}

export function useReminderDelivery({
  enabled = true,
  poll = true,
  focusRefresh = 'always',
}: UseReminderDeliveryOptions = {}) {
  return useQuery<ReminderDelivery, ApiError>({
    queryKey: REMINDER_DELIVERY_QUERY_KEY,
    queryFn: async () => (await fetchReminderDelivery()).delivery,
    enabled,
    retry: false,
    // Short enough that coming back from Discord (after fixing DM settings) refreshes the status.
    staleTime: 15_000,
    refetchOnWindowFocus:
      focusRefresh === 'always' ? true : (query) => query.state.data?.needsAttention === true,
    refetchInterval: poll ? (query) => deliveryPollInterval(query.state.data) : false,
  });
}
