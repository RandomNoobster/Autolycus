/**
 * Autolycus API Types
 *
 * This file contains TypeScript interfaces for all API responses and data structures.
 */

// ============================================================================
// Common Types
// ============================================================================

export interface ApiError {
  error: string;
  message: string;
  code: string;
}

export interface ApiResponse<T> {
  data: T | null;
  error: ApiError | null;
  isLoading: boolean;
}

// ============================================================================
// Raids Types
// ============================================================================

export interface RaidTarget {
  id: number;
  nationName: string;
  leaderName: string;
  allianceId: string;
  allianceName: string;
  alliancePosition: string;
  numCities: number;
  color: string;
  beigeTurns: number;
  nationLoot: string;
  daysInactive: number;
  monetaryNetIncome: number;
  netCashIncome: number;
  taxable: boolean;
  treasures: number;
  defSlots: number;
  timeSinceWar: string;
  soldiers: number;
  tanks: number;
  aircraft: number;
  ships: number;
  missiles: number;
  nukes: number;
  groundWin: number;
  airWin: number;
  navalWin: number;
  totalWin: number;
  hasReminderActive: boolean;
}

export interface AttackerInfo {
  id: number;
  nation_name: string;
  leader_name: string;
  score?: number;
}

export interface RaidsResponse {
  attacker: AttackerInfo;
  targets: RaidTarget[];
  beigeAlerts: string[];
  showBeige: boolean;
  generatedAt: string;
  discordLinked: boolean;
    warning?: string | null;
}

export interface ReminderRequest {
  nationId: number;
  beigeTurns?: number;
}

export interface ReminderResponse {
  success: boolean;
  message: string;
  nationId: number;
}

// ============================================================================
// Builds Types
// ============================================================================

export interface BuildData {
  // Template
  template: string;

  // Infrastructure
  infrastructure: number;
  impTotal: number;

  // Power plants
  coalpower: number;
  oilpower: number;
  windpower: number;
  nuclearpower: number;

  // Raw resource extraction
  coalmine: number;
  oilwell: number;
  uramine: number;
  leadmine: number;
  ironmine: number;
  bauxitemine: number;
  farm: number;

  // Manufacturing
  gasrefinery: number;
  aluminumrefinery: number;
  steelmill: number;
  munitionsfactory: number;

  // Civil improvements
  policestation: number;
  hospital: number;
  recyclingcenter: number;
  subway: number;
  supermarket: number;
  bank: number;
  mall: number;
  stadium: number;

  // Military
  barracks: number;
  factory: number;
  airforcebase: number;
  drydock: number;

  // Stats
  diseaseRate: number;
  realDiseaseRate: number;
  pollution: number;
  realPollution: number;
  crimeRate: number;
  realCrimeRate: number;
  commerce: number;
  realCommerce: number;
  mmr: string;

  // Income
  netIncome: number;
  netCash: number;
  unitUpkeep?: {
    included: boolean;
    total: number;
    food: number;
    breakdown: Record<string, number>;
    counts: Record<string, number>;
    mode: 'peace' | 'war';
    selectedMode?: 'peace' | 'war';
    modes?: Record<'peace' | 'war', { total: number; food: number; breakdown: Record<string, number> }>;
  };

  // Resource production
  aluminum: number;
  bauxite: number;
  coal: number;
  food: number;
  gasoline: number;
  iron: number;
  lead: number;
  munitions: number;
  oil: number;
  steel: number;
  uranium: number;

  // Population snapshot
  population?: number;
}

export interface BuildsResponse {
  builds: Record<string, BuildData>;
  resources: string[];
  land: number;
  uniqueBuilds: BuildData[];
  radiation?: {
    continent: Continent;
    raw: number;
    value: number;
  };
  foodModifiers?: {
    continent: Continent;
    seasonal: number;
    radiationMultiplier: number;
    combinedFoodMultiplier: number;
  };
  prices?: {
    mode: 'live' | 'average';
    live?: Record<string, number>;
    average30d?: Record<string, number> | null;
  };
  generatedAt: string;
}

// ============================================================================
// Builds Configuration Types
// ============================================================================

export type Continent = 'na' | 'sa' | 'eu' | 'af' | 'as' | 'au' | 'an';

export interface MilitaryBuildings {
  barracks: number;
  factory: number;
  airforcebase: number;
  drydock: number;
}

export interface NationData {
  id: number;
  name: string;
  leader: string;
  continent: Continent;
  cities: CityData[];
  projects: string[];
  policies: Record<string, string>;
}

export interface CityData {
  id: number;
  infrastructure: number;
  land: number;
  // Military buildings
  barracks: number;
  factory: number;
  airforcebase: number;
  drydock: number;
}

export interface BuildConfiguration {
  nationId?: number;
  infrastructure: number;
  land: number;
  continent: Continent;
  military: MilitaryBuildings;
  projects: string[];
  policies: string[];
  useLiveMarket: boolean;
  includeMilitaryUpkeep: boolean;
  domesticPolicy?: string;
  militaryUpkeepMode?: 'peace' | 'war';
}

export interface ContinentResources {
  continent: Continent;
  resources: string[];
  invalid: string[];
}

// ============================================================================
// Damage Types
// ============================================================================

export interface NationInfo {
  id: number;
  nationName: string;
  vds: boolean;
  irond: boolean;
  groundWinRate: number;
  airWinRate: number;
  navalWinRate: number;
}

export interface AttackStats {
  attackType: string;
  label: string;
  netDamage: number;
  damageDealt: number;
  damageReceived: number;
  gasConsumed: number;
  munConsumed: number;
  steelConsumed: number;
  alumConsumed: number;
  moneyUsed: number;
  infraDestroyed: number;
}

export interface NationAttacks {
  perResistance: AttackStats[];
  perMap: AttackStats[];
  totalStats: AttackStats[];
}

export interface NationDamageData {
  info: NationInfo;
  attacks: NationAttacks;
}

export interface ChartDataSeries {
  name: string;
  color: string;
}

export interface ChartDataPoint {
  attackType: string;
  [key: string]: string | number;
}

export interface ChartConfig {
  data: ChartDataPoint[];
  series: ChartDataSeries[];
}

export interface DamageChartData {
  netDamageComparison: ChartConfig;
}

export interface AttackTypeConfig {
  type: string;
  maps: number;
  label: string;
}

export interface DamageResponse {
  nation1: NationDamageData;
  nation2: NationDamageData;
  chartData: DamageChartData;
  attackTypes: AttackTypeConfig[];
  generatedAt: string;
}

// ============================================================================
// Resource Types (for icons)
// ============================================================================

export type ResourceType =
  | 'aluminum'
  | 'bauxite'
  | 'coal'
  | 'food'
  | 'gasoline'
  | 'iron'
  | 'lead'
  | 'money'
  | 'munitions'
  | 'oil'
  | 'steel'
  | 'uranium'
  | 'credits';

export const RESOURCE_ICONS: Record<ResourceType, string> = {
  aluminum: '/assets/resources/aluminum.png',
  bauxite: '/assets/resources/bauxite.png',
  coal: '/assets/resources/coal.png',
  food: '/assets/resources/food.png',
  gasoline: '/assets/resources/gasoline.png',
  iron: '/assets/resources/iron.png',
  lead: '/assets/resources/lead.png',
  money: '/assets/resources/money.png',
  munitions: '/assets/resources/munitions.png',
  oil: '/assets/resources/oil.png',
  steel: '/assets/resources/steel.png',
  uranium: '/assets/resources/uranium.png',
  credits: '/assets/resources/credits.png',
};
