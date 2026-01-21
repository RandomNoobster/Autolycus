/**
 * Damage API Functions
 */

import { apiGet, apiPost } from './client';
import type { DamageCalculationInput, DamageResponse } from '@/types';

/**
 * Fetch damage calculator data.
 *
 * @param nation1Id - First nation ID
 * @param nation2Id - Second nation ID
 * @returns DamageResponse with attack analysis
 */
export function fetchDamage(nation1Id: number, nation2Id: number): Promise<DamageResponse> {
  return apiGet<DamageResponse>(`/api/damage/?nation1=${nation1Id}&nation2=${nation2Id}`);
}

/**
 * Calculate damage using custom inputs.
 */
export function calculateDamage(
  input: DamageCalculationInput
): Promise<DamageResponse> {
  return apiPost<DamageResponse, DamageCalculationInput>('/api/damage/calculate', input);
}

export interface NationSearchResult {
  value: string;
  label: string;
  id: string;
  nationName: string;
  leaderName: string;
}

export function searchNations(
  query: string,
  limit: number = 10
): Promise<NationSearchResult[]> {
  const params = new URLSearchParams();
  params.set('q', query);
  params.set('limit', String(limit));
  return apiGet<NationSearchResult[]>(`/api/damage/nations/search?${params.toString()}`);
}
