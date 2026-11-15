/**
 * Raids page filter state outside React: versioned localStorage (draft filters + extra,
 * table-only column filters), column-filter deep links in the URL, and the state the page
 * starts from.
 */

import type { MRT_ColumnFiltersState } from 'mantine-react-table';

import {
  applyMappedColumnFilters,
  buildMappedColumnFiltersFromDraft,
  buildRaidsDraftFromSearchParams,
  migrateLegacyRaidsDraftBlob,
  RAID_FILTER_URL_KEYS,
  type RaidsDraftFilters,
} from '@/lib/raidsDraftState';

export const RAIDS_FILTERS_LOCAL_STORAGE_KEY = 'autolycus-raids-filters-v1';

/** Sidebar / URL–backed columns; never stored in extraColumnFilters. */
export const RAIDS_MAPPED_FILTER_COLUMN_IDS = new Set([
  'allianceName',
  'beigeTurns',
  'defSlots',
  'daysInactive',
  'alliancePosition',
  'nationLoot',
]);

/** Data columns of the raids table, in their default order. */
export const RAIDS_TABLE_DATA_COLUMN_IDS = [
  'id',
  'nationName',
  'leaderName',
  'allianceName',
  'alliancePosition',
  'numCities',
  'score',
  'color',
  'beigeTurns',
  'reminder',
  'nationLoot',
  'daysInactive',
  'updatedAt',
  'monetaryNetIncome',
  'netCashIncome',
  'taxable',
  'treasures',
  'defSlots',
  'timeSinceWar',
  'soldiers',
  'tanks',
  'aircraft',
  'ships',
  'missiles',
  'nukes',
  'groundWin',
  'airWin',
  'navalWin',
  'totalWin',
] as const;

/** The value shape each table-only filter takes (what its MRT filter function expects). */
type ExtraFilterKind = 'text' | 'number' | 'boolean' | 'multi' | 'range';

const EXTRA_FILTER_KINDS: Record<string, ExtraFilterKind> = {
  id: 'text',
  nationName: 'text',
  leaderName: 'text',
  treasures: 'text',
  numCities: 'range',
  score: 'range',
  color: 'multi',
  monetaryNetIncome: 'number',
  netCashIncome: 'number',
  taxable: 'boolean',
  timeSinceWar: 'number',
  soldiers: 'number',
  tanks: 'number',
  aircraft: 'number',
  ships: 'number',
  missiles: 'number',
  nukes: 'number',
  groundWin: 'number',
  airWin: 'number',
  navalWin: 'number',
  totalWin: 'number',
};

/**
 * A table-only filter value in the shape its column expects, or undefined to drop it.
 * A wrong shape is not harmless: a string reaching a multi-select filter throws while the
 * table renders.
 */
export function normalizeExtraFilterValue(id: string, value: unknown): unknown {
  const kind = EXTRA_FILTER_KINDS[id];
  if (!kind) return undefined;
  if (kind === 'multi') {
    const parts = Array.isArray(value) ? value : typeof value === 'string' ? value.split(',') : [];
    const items = parts.map((v) => String(v).trim()).filter(Boolean);
    return items.length ? items : undefined;
  }
  if (kind === 'range') {
    if (!Array.isArray(value) || value.length !== 2) return undefined;
    const bounds = value.map((v) => (typeof v === 'number' ? v : Number(v)));
    return bounds.every((n) => Number.isFinite(n)) ? bounds : undefined;
  }
  if (kind === 'boolean') {
    if (value === true || value === 'true') return 'true';
    if (value === false || value === 'false') return 'false';
    return undefined;
  }
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  if (typeof value === 'string' && value.trim()) return value.trim();
  return undefined;
}

function normalizeExtraFilters(items: unknown): MRT_ColumnFiltersState {
  if (!Array.isArray(items)) return [];
  const out: MRT_ColumnFiltersState = [];
  for (const item of items) {
    if (!item || typeof item !== 'object') continue;
    const id = (item as { id?: unknown }).id;
    if (typeof id !== 'string' || out.some((f) => f.id === id)) continue;
    const value = normalizeExtraFilterValue(id, (item as { value?: unknown }).value);
    if (value !== undefined) out.push({ id, value });
  }
  return out;
}

export function pickPersistableExtras(columnFilters: MRT_ColumnFiltersState): MRT_ColumnFiltersState {
  return normalizeExtraFilters(columnFilters);
}

export type RaidsFiltersStorageV3 = {
  v: 3;
  draft: RaidsDraftFilters;
  extraColumnFilters: { id: string; value: unknown }[];
};

export function serializeRaidsFiltersStorageV3(
  draft: RaidsDraftFilters,
  columnFilters: MRT_ColumnFiltersState
): string {
  const payload: RaidsFiltersStorageV3 = {
    v: 3,
    draft,
    extraColumnFilters: pickPersistableExtras(columnFilters),
  };
  return JSON.stringify(payload);
}

export type ParsedRaidsStorage = {
  draftRecord: Record<string, unknown>;
  extras: MRT_ColumnFiltersState;
};

/**
 * Parse localStorage JSON: v2/v3 envelope or legacy v1 draft-only blob.
 */
export function parseRaidsFiltersStorageJson(parsed: unknown): ParsedRaidsStorage | null {
  if (!parsed || typeof parsed !== 'object') return null;
  const o = parsed as Record<string, unknown>;

  if ((o.v === 2 || o.v === 3) && o.draft && typeof o.draft === 'object') {
    return {
      draftRecord: o.draft as Record<string, unknown>,
      extras: normalizeExtraFilters(o.extraColumnFilters),
    };
  }

  return {
    draftRecord: o,
    extras: [],
  };
}

function readStoredRaidsFilters(): ParsedRaidsStorage | null {
  try {
    const raw = localStorage.getItem(RAIDS_FILTERS_LOCAL_STORAGE_KEY);
    return raw ? parseRaidsFiltersStorageJson(JSON.parse(raw)) : null;
  } catch (error) {
    console.warn('Failed to restore raids filters', error);
    return null;
  }
}

/** Mapped column ids whose deep-link values are lists. */
const LIST_MAPPED_COLUMN_IDS = new Set(['allianceName', 'alliancePosition']);

/**
 * Column filters given as query params (`?soldiers=50000`, `?color=beige,red`): table-only
 * filters shaped for their column, and sidebar (mapped) filters for the draft. Unknown
 * params are ignored.
 */
export function columnFiltersFromSearchParams(sp: URLSearchParams): {
  extras: MRT_ColumnFiltersState;
  mapped: MRT_ColumnFiltersState;
} {
  const extras: MRT_ColumnFiltersState = [];
  const mapped: MRT_ColumnFiltersState = [];
  for (const id of RAIDS_TABLE_DATA_COLUMN_IDS) {
    const raw = sp.get(id);
    if (raw === null || !raw.trim()) continue;
    if (RAIDS_MAPPED_FILTER_COLUMN_IDS.has(id)) {
      const value = LIST_MAPPED_COLUMN_IDS.has(id)
        ? raw.split(',').map((s) => s.trim()).filter(Boolean)
        : raw.trim();
      mapped.push({ id, value });
      continue;
    }
    const value = normalizeExtraFilterValue(
      id,
      EXTRA_FILTER_KINDS[id] === 'range' ? raw.split(',') : raw
    );
    if (value !== undefined) extras.push({ id, value });
  }
  return { extras, mapped };
}

function hasDraftParams(sp: URLSearchParams): boolean {
  return RAID_FILTER_URL_KEYS.some((key) =>
    key === 'alliance' || key === 'allianceExclude'
      ? sp.getAll(key).some(Boolean)
      : sp.get(key) !== null
  );
}

/**
 * The filters the page starts with. The sidebar comes from the URL when it has draft params
 * (a reload or shared link), else from storage. Table-only filters always come from storage,
 * since they are never in the URL, plus any column-filter deep links in the URL.
 */
export function loadInitialRaidsFilters(
  sp: URLSearchParams,
  savedNationId: string | undefined
): { draft: RaidsDraftFilters; columnFilters: MRT_ColumnFiltersState } {
  const stored = readStoredRaidsFilters();
  let draft = buildRaidsDraftFromSearchParams(sp, savedNationId, '');
  if (!hasDraftParams(sp) && stored) {
    draft = { ...draft, ...migrateLegacyRaidsDraftBlob(stored.draftRecord) };
  }

  const fromUrl = columnFiltersFromSearchParams(sp);
  if (fromUrl.mapped.length) {
    draft = applyMappedColumnFilters(draft, fromUrl.mapped, fromUrl.mapped.map((f) => f.id));
  }

  const extras = new Map<string, unknown>();
  for (const f of stored?.extras ?? []) extras.set(f.id, f.value);
  for (const f of fromUrl.extras) extras.set(f.id, f.value);

  return {
    draft,
    columnFilters: [
      ...Array.from(extras, ([id, value]) => ({ id, value })),
      ...buildMappedColumnFiltersFromDraft(draft),
    ],
  };
}
