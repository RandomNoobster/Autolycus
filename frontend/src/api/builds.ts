/**
 * Builds API Functions
 */

import type { BuildsResponse, NationData, BuildConfiguration } from '@/types';
import type { GameDataResponse } from '@/types/gameData';

/**
 * Fetch city builds data.
 *
 * @param config - Build configuration parameters
 * @returns BuildsResponse with build templates
 */
export async function fetchBuilds(config: BuildConfiguration): Promise<BuildsResponse> {
  const params = new URLSearchParams();
  
  // Required: Use nation_id or default to 1 for testing
  if (config.nationId) {
    params.set('nation_id', config.nationId.toString());
  } else {
    // For manual configuration, we still need a nation ID for the API
    // Use a placeholder that won't affect the calculation
    params.set('nation_id', '1');
  }
  
  params.set('infra', config.infrastructure.toString());
  params.set('land', config.land.toString());
  params.set('continent', config.continent);
  params.set('use_live_prices', config.useLiveMarket.toString());
  params.set('include_military_upkeep', config.includeMilitaryUpkeep.toString());
  if (config.militaryUpkeepMode) {
    params.set('military_upkeep_mode', config.militaryUpkeepMode);
  }
  if (config.projects?.length) {
    params.set('projects', config.projects.join(','));
  }
  if (config.domesticPolicy) {
    params.set('domestic_policy', config.domesticPolicy);
  }
  
  // Format MMR
  const mmr = `${config.military.barracks}/${config.military.factory}/${config.military.airforcebase}/${config.military.drydock}`;
  params.set('mmr', mmr);
  
  const response = await fetch(`http://localhost:5000/api/builds/?${params}`);
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || 'Failed to fetch builds');
  }
  
  return response.json();
}

/**
 * Fetch nation data for build configuration.
 *
 * @param nationId - The nation ID to fetch
 * @returns NationData with infrastructure, continent, projects, etc.
 */
export async function fetchNationData(nationId: number): Promise<NationData> {
  const response = await fetch(`http://localhost:5000/api/builds/nation/${nationId}`);
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || 'Failed to fetch nation data');
  }
  
  return response.json();
}

/**
 * Fetch game data (projects and policies).
 *
 * @returns GameDataResponse with projects, war policies, and domestic policies
 */
export async function fetchGameData(): Promise<GameDataResponse> {
  const response = await fetch('http://localhost:5000/api/builds/game-data');
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || 'Failed to fetch game data');
  }
  
  return response.json();
}
