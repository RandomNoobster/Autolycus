/**
 * Builds API Functions
 */

import type { BuildsResponse, NationData, BuildConfiguration } from '@/types';
import type { GameDataResponse } from '@/types/gameData';
import { formatMMR } from '@/utils/format';
import { apiGet, withQuery } from './client';

/** The API parses these with int(): send whole numbers (form inputs allow decimals and blanks). */
function wholeNumber(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? Math.round(n) : Number.NaN;
}

function buildingCount(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? Math.max(0, Math.trunc(n)) : 0;
}

/**
 * Fetch city builds data.
 *
 * @param config - Build configuration parameters
 * @returns BuildsResponse with build templates
 */
export async function fetchBuilds(config: BuildConfiguration): Promise<BuildsResponse> {
  const { military } = config;
  return apiGet<BuildsResponse>(
    withQuery('/api/builds/', {
      nation_id: config.nationId || undefined,
      infra: wholeNumber(config.infrastructure),
      land: wholeNumber(config.land),
      continent: config.continent,
      use_live_prices: config.useLiveMarket,
      include_military_upkeep: config.includeMilitaryUpkeep,
      disable_population_income: config.disablePopulationIncome,
      military_upkeep_mode: config.militaryUpkeepMode || undefined,
      // Always send projects/policy so cleared form values override the nation profile.
      projects: (config.projects ?? []).join(','),
      domestic_policy: config.domesticPolicy ?? '',
      mmr: formatMMR(
        buildingCount(military.barracks),
        buildingCount(military.factory),
        buildingCount(military.airforcebase),
        buildingCount(military.drydock)
      ),
    })
  );
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
 * Fetch game data (projects and domestic policies).
 *
 * @returns GameDataResponse with projects and domestic policies
 */
export async function fetchGameData(): Promise<GameDataResponse> {
  return apiGet<GameDataResponse>('/api/builds/game-data');
}
