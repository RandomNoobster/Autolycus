/**
 * Builds API Functions
 */

import type { BuildsResponse, NationData, BuildConfiguration } from '@/types';
import type { GameDataResponse } from '@/types/gameData';
import { apiGet } from './client';

/**
 * Fetch city builds data.
 *
 * @param config - Build configuration parameters
 * @returns BuildsResponse with build templates
 */
export async function fetchBuilds(config: BuildConfiguration): Promise<BuildsResponse> {
  const params = new URLSearchParams();

  if (config.nationId) {
    params.set('nation_id', config.nationId.toString());
  }

  params.set('infra', config.infrastructure.toString());
  params.set('land', config.land.toString());
  params.set('continent', config.continent);
  params.set('use_live_prices', config.useLiveMarket.toString());
  params.set('include_military_upkeep', config.includeMilitaryUpkeep.toString());
  params.set('disable_population_income', config.disablePopulationIncome.toString());
  if (config.militaryUpkeepMode) {
    params.set('military_upkeep_mode', config.militaryUpkeepMode);
  }

  // Always send projects/policy so cleared form values override the nation profile.
  params.set('projects', (config.projects ?? []).join(','));
  params.set('domestic_policy', config.domesticPolicy ?? '');

  // Format MMR
  const mmr = `${config.military.barracks}/${config.military.factory}/${config.military.airforcebase}/${config.military.drydock}`;
  params.set('mmr', mmr);

  return apiGet<BuildsResponse>(`/api/builds/?${params.toString()}`);
}

/**
 * Fetch nation data for build configuration.
 *
 * @param nationId - The nation ID to fetch
 * @returns NationData with infrastructure, continent, projects, etc.
 */
export async function fetchNationData(nationId: number): Promise<NationData> {
  return apiGet<NationData>(`/api/builds/nation/${nationId}`);
}

/**
 * Fetch game data (projects and policies).
 *
 * @returns GameDataResponse with projects, war policies, and domestic policies
 */
export async function fetchGameData(): Promise<GameDataResponse> {
  return apiGet<GameDataResponse>('/api/builds/game-data');
}
