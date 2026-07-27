/**
 * Nuke Targets API
 *
 * GET /api/nuke-targets/ accepts score bounds and optional attackerNationId.
 * Alliance, beige, infra, and similar filters are applied client-side.
 */

import { apiGet } from './client';
import type { NukeTargetsResponse } from '@/types';

export interface NukeTargetFilterParams {
  attackerNationId?: number;
  minScore?: number;
  maxScore?: number;
  vmode?: boolean;
}

export function fetchNukeTargets(
  filters: NukeTargetFilterParams = {}
): Promise<NukeTargetsResponse> {
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
  const endpoint = qs ? `/api/nuke-targets/?${qs}` : '/api/nuke-targets/';
  return apiGet<NukeTargetsResponse>(endpoint);
}
