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
  /** Seconds from the `Retry-After` header, when the server sent one (e.g. 429 RATE_LIMITED). */
  retryAfterSeconds?: number;
}

export interface ApiResponse<T> {
  data: T | null;
  error: ApiError | null;
  isLoading: boolean;
}

// ============================================================================
// Raids Types (GET /api/raids/ — table filters are client-side on RaidsPage)
// ============================================================================

export interface RaidTarget {
  id: number;
  nationName: string;
  leaderName: string;
  allianceId: string;
  allianceName: string;
  alliancePosition: string;
  numCities: number;
  score: number;
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
  updatedAt?: number | null;
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
  generatedAt: string;
  discordAuthenticated: boolean;
  discordLinked: boolean;
    warning?: string | null;
}

// ============================================================================
// Nuke Targets Types (GET /api/nuke-targets/)
// ============================================================================

export interface NukeTarget {
  id: number;
  nationName: string;
  leaderName: string;
  allianceId: string;
  allianceName: string;
  alliancePosition: string;
  numCities: number;
  score: number;
  color: string;
  beigeTurns: number;
  daysInactive: number;
  defSlots: number;
  timeSinceWar: string;
  soldiers: number;
  tanks: number;
  aircraft: number;
  ships: number;
  missiles: number;
  nukes: number;
  maxInfra?: number;
  avgInfra?: number;
  nukeInfraLost?: number;
  nukeDamage?: number;
  nukeDamageWithoutVds?: number;
  nukeNet?: number;
  missileInfraLost?: number;
  missileDamage?: number;
  missileDamageWithoutIronDome?: number;
  missileNet?: number;
  simNukeNet?: number;
  simNukeShots?: number;
  simMissileNet?: number;
  simMissileShots?: number;
  vds?: boolean;
  ironDome?: boolean;
  falloutShelter?: boolean;
  defenderWarPolicy?: string;
}

export interface NukeTargetsAttackerInfo extends AttackerInfo {
  /** Nation's actual war policy from cache. */
  warpolicy?: string;
  /** Nation's actual Guiding Satellite project from cache. */
  guidingSatellite?: boolean;
  /** War policy used for damage math after overrides. */
  effectiveWarPolicy?: string;
  /** Guiding Satellite flag used for damage math after overrides. */
  effectiveGuidingSatellite?: boolean;
  /** Whether Attrition is applied in damage math. */
  attrition?: boolean;
}

export interface NukeTargetsAssumptions {
  warType: string;
  warRole: string;
  resistanceModel: string;
  dollarDamage: string;
  attackerAttrition?: boolean | null;
  attackerGuidingSatellite?: boolean | null;
}

export interface NukeTargetsResponse {
  attacker: NukeTargetsAttackerInfo | null;
  targets: NukeTarget[];
  generatedAt: string;
  discordAuthenticated: boolean;
  discordLinked: boolean;
  assumptions: NukeTargetsAssumptions;
  warning?: string | null;
}

export interface ReminderRequest {
  nationId: number;
}

export interface ReminderResponse {
  success: boolean;
  message: string;
  nationId: number;
  beigeAlerts?: string[];
  beigeAlertConfig?: number[];
  /** Delivery status after the change (POST and DELETE). */
  delivery?: ReminderDelivery;
  /** POST only: non-null when a test DM was queued automatically. */
  testDm?: TestDmStatus | null;
}

export interface ReminderNation {
  nationId: number;
  nationName: string;
  leaderName: string;
  beigeTurns: number;
  vacationModeTurns: number;
  /** Expected beige/vacation mode exit (ISO 8601 UTC); null until the scheduler has planned it. */
  exitAt: string | null;
  /** Next planned reminder (ISO 8601 UTC); null until the scheduler has planned it. */
  nextReminderAt: string | null;
}

export interface RemindersResponse {
  success: boolean;
  reminders: ReminderNation[];
  beigeAlerts: string[];
  beigeAlertConfig: number[];
  delivery: ReminderDelivery;
}

export interface ReminderConfigRequest {
  beigeAlertConfig: number[];
}

export interface ReminderConfigResponse {
  success: boolean;
  message: string;
  beigeAlerts: string[];
  beigeAlertConfig: number[];
}

// ============================================================================
// Reminder delivery (Discord DM + browser push)
// ============================================================================

export interface ReminderChannels {
  discordDm: boolean;
  webPush: boolean;
}

export type DmDeliveryState = 'unknown' | 'pending' | 'ok' | 'confirmed' | 'failed';

export type DmFailureReason = 'no_mutual_server' | 'dms_closed' | 'unknown_user' | 'other';

export interface DmDeliveryStatus {
  /** unknown = never tried; pending = test DM queued/sending */
  state: DmDeliveryState;
  /** Discord JSON error code of the last failure (50278, 50007, 10013, ...) */
  code: number | null;
  /** 50278 → no_mutual_server, 50007 → dms_closed, 10013 → unknown_user */
  reason: DmFailureReason | null;
  lastAttemptAt: string | null;
  lastSuccessAt: string | null;
  lastFailureAt: string | null;
  /** When the user clicked "Got it" in a test DM */
  confirmedAt: string | null;
}

export type TestDmState = 'queued' | 'sending' | 'sent' | 'failed' | 'confirmed';

export interface TestDmStatus {
  id: string;
  state: TestDmState;
  code: number | null;
  reason: DmFailureReason | null;
  requestedAt: string;
  sentAt: string | null;
  confirmedAt: string | null;
}

export type ReminderProblemKind =
  /** Every enabled channel failed (reminderRemoved tells whether the reminder was removed) */
  | 'not_delivered'
  /** Discord refused the DM, push delivered → reminder kept */
  | 'dm_refused'
  /** Push failed on every device, DM delivered → reminder kept */
  | 'push_failed'
  /** Nation wasn't in beige or vacation mode → reminder removed */
  | 'not_protected'
  /** Nation no longer exists → reminder removed */
  | 'nation_missing';

export interface ReminderProblem {
  kind: ReminderProblemKind;
  nationId: string;
  nationName: string | null;
  offsetMinutes: number | null;
  dueAt: string | null;
  code: number | null;
  reminderRemoved: boolean;
  at: string;
}

export interface ReminderDelivery {
  channels: ReminderChannels;
  dm: DmDeliveryStatus;
  latestTestDm: TestDmStatus | null;
  /** configured=false → the server has no push keys */
  push: { configured: boolean; deviceCount: number };
  /** Newest first, max 10 */
  recentProblems: ReminderProblem[];
  supportInviteUrl: string;
  /** True when an enabled channel is broken (DM on + failed, or push on with 0 devices) */
  needsAttention: boolean;
}

export interface PushDevice {
  /** First 32 hex chars of SHA-256(endpoint) */
  id: string;
  label: string;
  createdAt: string;
  lastSeenAt: string | null;
  lastSuccessAt: string | null;
  lastFailureAt: string | null;
}

export interface ReminderDeliveryResponse {
  success: boolean;
  delivery: ReminderDelivery;
}

export type ReminderChannelsRequest = ReminderChannels;

export interface ReminderChannelsResponse {
  success: boolean;
  message: string;
  delivery: ReminderDelivery;
}

export interface TestDmResponse {
  success: boolean;
  message: string;
  testDm: TestDmStatus;
  delivery: ReminderDelivery;
}

export interface PushVapidKeyResponse {
  /** base64url-encoded application server key */
  publicKey: string;
  keyId: string;
}

export interface PushDevicesResponse {
  success: boolean;
  devices: PushDevice[];
  configured: boolean;
  keyId: string | null;
}

export interface PushDeviceRegisterRequest {
  endpoint: string;
  keys: { p256dh: string; auth: string };
  keyId?: string;
  label?: string;
  /** Default true: also switches the webPush channel on */
  enableChannel?: boolean;
}

export interface PushDeviceRegisterResponse {
  success: boolean;
  device: PushDevice;
  delivery: ReminderDelivery;
}

export interface PushDeviceRemoveResponse {
  success: boolean;
  removed: boolean;
  delivery: ReminderDelivery;
}

export interface PushTestResponse {
  success: boolean;
  sent: number;
  failed: number;
  removed: number;
}

export interface VerifyLinkRequest {
  nationId: string;
}

export interface VerifyLinkResponse {
  success: boolean;
  code: string;
  message: string;
  nationId?: string | null;
  relinked?: boolean;
}

export interface LinkedNationResponse {
  authenticated: boolean;
  linked: boolean;
  nation_id?: string | null;
  nation_name?: string | null;
  flag_url?: string | null;
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
  netIncomeReal?: number;
  netCash: number;
  netCashReal?: number;
  unitUpkeep?: {
    included: boolean;
    total: number;
    food: number;
    breakdown: Record<string, number>;
    breakdownFood?: Record<string, number>;
    counts: Record<string, number>;
    mode: 'peace' | 'war';
    selectedMode?: 'peace' | 'war';
    modes?: Record<
      'peace' | 'war',
      { total: number; food: number; breakdown: Record<string, number>; breakdownFood?: Record<string, number> }
    >;
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
  disablePopulationIncome: boolean;
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
  numCities: number;
  /** P&W nation flag image URL when available from the battle query. */
  flagUrl?: string | null;
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
  uraniumConsumed: number;
  foodConsumed: number;
  moneyUsed: number;
  infraDestroyed: number;
}

export interface AttackStatsSet {
  perAttack: AttackStats[];
  perResistance: AttackStats[];
  perMap: AttackStats[];
}

export interface DamageScenarioSide {
  info: NationInfo;
  stats: AttackStatsSet;
}

export interface DamageScenario {
  attacker: DamageScenarioSide;
  defender: DamageScenarioSide;
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

export type DamageWarType = 'RAID' | 'ORDINARY' | 'ATTRITION';

export interface DamageNationInput {
  id: number;
  soldiers: number;
  tanks: number;
  aircraft: number;
  ships: number;
  missiles: number;
  nukes: number;
  warpolicy: string;
  vds: boolean;
  irond: boolean;
  falloutShelter: boolean;
  guidingSatellite: boolean;
  militarySalvage: boolean;
  advancedPirateEconomy: boolean;
  soldiersUseMunitions: boolean;
  cityInfrastructure: number;
  cityLand: number;
}

export interface DamageWarInput {
  attackerId: number;
  defenderId: number;
  warType: DamageWarType;
  groundControlId?: number | null;
  airSuperiorityId?: number | null;
  navalBlockadeId?: number | null;
  /** Fortified modifier for the nation in calculator slot 1 (URL/query nation1). */
  nation1Fortified: boolean;
  /** Fortified modifier for the nation in calculator slot 2 (URL/query nation2). */
  nation2Fortified: boolean;
  attackerPeace: boolean;
  defenderPeace: boolean;
}

/** One active war row from GET /api/damage/linked-active-wars (preset for calculator). */
export interface DamageLinkedWarPreset {
  war_id: number | null;
  attacker_id: number;
  defender_id: number;
  opponent_id: number;
  opponent_name: string;
  opponent_flag_url: string | null;
  opponent_alliance_name: string | null;
  opponent_alliance_flag_url: string | null;
  /** Linked nation is war declarer (attacker) vs defender. */
  linked_stance: 'offensive' | 'defensive';
  /** Opponent’s remaining resistance (game scale 0–100). */
  enemy_resistance?: number;
  /** Your Military Action Points remaining (max 12). */
  your_maps?: number;
  /** Older API responses used these names (same semantics as enemy_resistance / your_maps). */
  linked_resistance?: number;
  linked_maps?: number;
  war: DamageWarInput;
}

export interface DamageLinkedActiveWarsResponse {
  linked: boolean;
  nation_id: string | null;
  wars: DamageLinkedWarPreset[];
}

/** GET /api/stats/public */
export interface PublicStatsResponse {
  /** Count of MongoDB ``global_users`` documents; null if unavailable. */
  registered_users: number | null;
}

export interface DamageCalculationInput {
  nation1Id: number;
  nation2Id: number;
  nation1: DamageNationInput;
  nation2: DamageNationInput;
  war: DamageWarInput;
}

export interface DamageResponse {
  nations: {
    nation1: NationInfo;
    nation2: NationInfo;
  };
  scenarios: {
    nation1Attacks: DamageScenario;
    nation2Attacks: DamageScenario;
  };
  chartData: DamageChartData;
  attackTypes: AttackTypeConfig[];
  inputs: DamageCalculationInput;
  generatedAt: string;
  warStatus?: {
    nation1Modifiers: string;
    nation2Modifiers: string;
    groundControl: string | null;
  };
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
