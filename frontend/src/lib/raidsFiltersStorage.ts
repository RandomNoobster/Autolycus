/**
 * Versioned localStorage for raids page: draft filters + extra (non-mapped) MRT column filters.
 */

import type { MRT_ColumnFiltersState } from 'mantine-react-table';

import type { RaidsDraftFilters } from '@/lib/raidsDraftState';

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

const RAIDS_TABLE_DATA_COLUMN_IDS: readonly string[] = [
  'id',
  'nationName',
  'leaderName',
  'allianceName',
  'alliancePosition',
  'numCities',
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
];

export const RAIDS_STORABLE_EXTRA_COLUMN_IDS = new Set(
  RAIDS_TABLE_DATA_COLUMN_IDS.filter((id) => !RAIDS_MAPPED_FILTER_COLUMN_IDS.has(id))
);

export type RaidsFiltersStorageV2 = {
  v: 2;
  draft: RaidsDraftFilters;
  extraColumnFilters: { id: string; value: unknown }[];
};

function isPersistableExtraValue(val: unknown): boolean {
  if (val === null || typeof val === 'string' || typeof val === 'number' || typeof val === 'boolean') {
    return true;
  }
  if (Array.isArray(val) && val.every((x) => typeof x === 'string')) {
    return true;
  }
  return false;
}

const KNOWN_COLUMN_ID_SET = new Set(RAIDS_TABLE_DATA_COLUMN_IDS);

export function sanitizeExtraColumnFiltersForRestore(raw: unknown): MRT_ColumnFiltersState {
  if (!Array.isArray(raw)) return [];
  const out: MRT_ColumnFiltersState = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue;
    const id = (item as { id?: unknown }).id;
    if (typeof id !== 'string' || !KNOWN_COLUMN_ID_SET.has(id)) continue;
    if (RAIDS_MAPPED_FILTER_COLUMN_IDS.has(id)) continue;
    const value = (item as { value?: unknown }).value;
    if (!isPersistableExtraValue(value)) {
      if (import.meta.env.DEV) {
        console.warn('[raidsFiltersStorage] skipped non-persistable extra filter', id, value);
      }
      continue;
    }
    out.push({ id, value });
  }
  return out;
}

export function pickPersistableExtras(columnFilters: MRT_ColumnFiltersState): MRT_ColumnFiltersState {
  return columnFilters.filter(
    (f) =>
      RAIDS_STORABLE_EXTRA_COLUMN_IDS.has(f.id) &&
      isPersistableExtraValue(f.value)
  );
}

export function serializeRaidsFiltersStorageV2(
  draft: RaidsDraftFilters,
  columnFilters: MRT_ColumnFiltersState
): string {
  const payload: RaidsFiltersStorageV2 = {
    v: 2,
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
 * Parse localStorage JSON: v2 envelope or legacy v1 draft-only blob.
 */
export function parseRaidsFiltersStorageJson(parsed: unknown): ParsedRaidsStorage | null {
  if (!parsed || typeof parsed !== 'object') return null;
  const o = parsed as Record<string, unknown>;

  if (o.v === 2 && o.draft && typeof o.draft === 'object') {
    return {
      draftRecord: o.draft as Record<string, unknown>,
      extras: sanitizeExtraColumnFiltersForRestore(o.extraColumnFilters),
    };
  }

  return {
    draftRecord: o,
    extras: [],
  };
}
