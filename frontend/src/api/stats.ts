/**
 * Public aggregate stats API
 */

import { apiGet } from './client';
import type { PublicStatsResponse } from '@/types';

/** Registered user count from Mongo ``global_users`` (public). */
export function fetchPublicStats(): Promise<PublicStatsResponse> {
  return apiGet<PublicStatsResponse>('/api/stats/public');
}
