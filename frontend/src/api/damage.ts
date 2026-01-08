/**
 * Damage API Functions
 */

import { apiGet } from './client';
import type { DamageResponse } from '@/types';

/**
 * Fetch damage calculator data.
 *
 * @param token - The authentication token from the URL
 * @returns DamageResponse with attack analysis
 */
export function fetchDamage(token: string): Promise<DamageResponse> {
  return apiGet<DamageResponse>('/api/damage/', token);
}
