/**
 * Continent and Resource Utilities
 *
 * Functions for determining valid resources based on continent.
 */

import type { Continent, ContinentResources } from '@/types';

/**
 * Continent resource mappings.
 * Source: fandom_data.jsonl - continent-specific articles
 * Each continent has exactly 3 raw resources available.
 * All continents can produce manufactured resources and food.
 */
const CONTINENT_RESOURCE_MAP: Record<Continent, string[]> = {
  na: ['coal', 'iron', 'uranium'],  // North America
  sa: ['oil', 'bauxite', 'lead'],   // South America
  eu: ['coal', 'iron', 'lead'],     // Europe
  af: ['oil', 'bauxite', 'uranium'], // Africa
  as: ['oil', 'iron', 'uranium'],   // Asia
  au: ['coal', 'bauxite', 'lead'],  // Australia
  an: ['coal', 'oil', 'uranium'],   // Antarctica
};

/**
 * Manufactured resources (available on all continents).
 */
const MANUFACTURED_RESOURCES = ['gasoline', 'munitions', 'steel', 'aluminum'];

/**
 * Universal resources (not affected by continent).
 */
const UNIVERSAL_RESOURCES = ['food', 'net income', 'money'];

/**
 * Get the resources a continent can produce.
 *
 * @param continent - The continent code
 * @returns The continent and its producible resources
 */
export function getContinentResources(continent: Continent): ContinentResources {
  return {
    continent,
    resources: [...getContinentRawResources(continent), ...MANUFACTURED_RESOURCES, ...UNIVERSAL_RESOURCES],
  };
}

/**
 * Get raw resources available for a continent.
 *
 * @param continent - The continent code
 * @returns Array of raw resource names
 */
export function getContinentRawResources(continent: Continent): string[] {
  return CONTINENT_RESOURCE_MAP[continent] || [];
}

/**
 * Check if a resource is valid for a continent.
 *
 * @param resource - The resource name
 * @param continent - The continent code
 * @returns True if the resource can be produced on this continent
 */
export function isResourceValid(resource: string, continent: Continent): boolean {
  const { resources } = getContinentResources(continent);
  return resources.includes(resource);
}

/**
 * All continents for dropdown.
 */
export const CONTINENTS: Array<{ value: Continent; label: string }> = [
  { value: 'na', label: 'North America' },
  { value: 'sa', label: 'South America' },
  { value: 'eu', label: 'Europe' },
  { value: 'af', label: 'Africa' },
  { value: 'as', label: 'Asia' },
  { value: 'au', label: 'Australia' },
  { value: 'an', label: 'Antarctica' },
];
