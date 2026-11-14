/**
 * Nuke Targets API
 *
 * GET /api/nuke-targets/ accepts score bounds, optional attackerNationId, and
 * an optional Guiding Satellite override (guidingSatellite).
 * Alliance, beige, infra, and similar filters are applied client-side.
 */

import { apiGet, withQuery } from './client';
import type { RaidFilterParams } from './raids';
import type { NukeTargetsResponse } from '@/types';

export type NukeTargetFilterParams = RaidFilterParams & {
  /** When set, force Guiding Satellite on/off for damage math (+20% nuke/missile infra). */
  guidingSatellite?: boolean;
};

export function fetchNukeTargets(
  filters: NukeTargetFilterParams = {},
  signal?: AbortSignal
): Promise<NukeTargetsResponse> {
  return apiGet<NukeTargetsResponse>(withQuery('/api/nuke-targets/', filters), signal);
}
