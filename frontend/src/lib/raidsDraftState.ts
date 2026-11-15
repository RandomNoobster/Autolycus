import type { MRT_ColumnFiltersState } from 'mantine-react-table';

import {
  classifyAlliancePositionFilter,
  classifyInactiveColumnValue,
  classifyLootColumnValue,
  INACTIVE_PRESET_DAYS,
  normalizeDefSlotsFilterValue,
  parseNumericValue,
  positionsArrayKey,
} from '@/lib/raidFilterParsing';
import { warRangeQueryBounds } from '@/lib/warRange';

export type RaidsDraftFilters = {
  allianceMode: 'include' | 'exclude';
  alliance: string[];
  /** Used when allianceMode is 'exclude'. */
  allianceExclude: string[];
  beige: 'all' | 'only' | 'hide';
  maxWars: string;
  inactiveMode: 'none' | 'preset' | 'custom';
  inactivePreset: string;
  inactiveCustom: string;
  lootMode: 'none' | 'preset' | 'custom';
  lootPreset: string;
  lootCustom: string;
  scopeMode: 'preset' | 'custom';
  scopePreset: 'all' | 'apps_or_none' | 'no_alliance';
  scopeCustomPositions: string[];
  performance: boolean;
  scoreMode: string;
  yourScore: string;
  minScore: string;
  maxScore: string;
};

export const DEFAULT_RAIDS_DRAFT_FILTERS = (
  scoreDefaults: { scoreMode: string; yourScore: string }
): RaidsDraftFilters => ({
  allianceMode: 'include',
  alliance: [],
  allianceExclude: [],
  beige: 'all',
  maxWars: 'all',
  inactiveMode: 'none',
  inactivePreset: '3',
  inactiveCustom: '',
  lootMode: 'none',
  lootPreset: '0',
  lootCustom: '',
  scopeMode: 'preset',
  scopePreset: 'all',
  scopeCustomPositions: [],
  performance: false,
  scoreMode: scoreDefaults.scoreMode,
  yourScore: scoreDefaults.yourScore,
  minScore: '',
  maxScore: '',
});

function parseAlliancesFromSearchParams(sp: URLSearchParams, key: 'alliance' | 'allianceExclude' = 'alliance'): string[] {
  const raw = sp.getAll(key).map((s) => s.trim()).filter(Boolean);
  return [...new Set(raw)];
}

function parseBooleanParam(sp: URLSearchParams, key: string): boolean | undefined {
  const val = sp.get(key);
  if (val === null) return undefined;
  return val === 'true' || val === '1';
}

/**
 * Raids writes beige=true|false; Nuke Targets writes beige=all|only|hide (the navbar can carry
 * either page's query to the other). Anything else means all.
 */
function parseBeigeParam(sp: URLSearchParams): RaidsDraftFilters['beige'] {
  const val = sp.get('beige');
  if (val === 'true' || val === '1' || val === 'only') return 'only';
  if (val === 'false' || val === '0' || val === 'hide') return 'hide';
  return 'all';
}

function parseNumberParam(sp: URLSearchParams, key: string): number | undefined {
  const val = sp.get(key);
  if (val === null || val === '') return undefined;
  const num = Number(val);
  return Number.isNaN(num) ? undefined : num;
}

export function buildRaidsDraftFromSearchParams(
  sp: URLSearchParams,
  savedNationId: string | undefined,
  nationScore: string
): RaidsDraftFilters {
  const base = DEFAULT_RAIDS_DRAFT_FILTERS({
    scoreMode: sp.get('scoreMode') || (savedNationId ? 'yours' : 'custom'),
    yourScore: sp.get('yourScore') || nationScore || '',
  });

  const modeRaw = sp.get('allianceMode');
  const allianceMode: RaidsDraftFilters['allianceMode'] =
    modeRaw === 'exclude' ? 'exclude' : 'include';

  const draft: RaidsDraftFilters = {
    ...base,
    allianceMode,
    alliance: parseAlliancesFromSearchParams(sp, 'alliance'),
    allianceExclude: parseAlliancesFromSearchParams(sp, 'allianceExclude'),
    beige: parseBeigeParam(sp),
    maxWars: (() => {
      const n = parseNumberParam(sp, 'maxWars');
      if (n === undefined) return 'all';
      // 3 means "any" (same as omitting maxWars); sidebar no longer exposes 3 as its own option.
      if (n === 3) return 'all';
      if (n >= 0 && n <= 2) return String(n);
      return 'all';
    })(),
    performance: parseBooleanParam(sp, 'performance') ?? false,
    minScore: sp.get('minScore') || '',
    maxScore: sp.get('maxScore') || '',
  };

  const inactiveRaw = sp.get('inactiveMinDays');
  if (inactiveRaw !== null && inactiveRaw !== '') {
    const c = classifyInactiveColumnValue(inactiveRaw);
    draft.inactiveMode = c.inactiveMode;
    draft.inactivePreset = c.inactivePreset;
    draft.inactiveCustom = c.inactiveCustom;
  }

  const lootRaw = sp.get('minBeigeLoot');
  if (lootRaw !== null && lootRaw !== '') {
    const c = classifyLootColumnValue(lootRaw);
    draft.lootMode = c.lootMode;
    draft.lootPreset = c.lootPreset;
    draft.lootCustom = c.lootCustom;
  }

  const positionsRaw = sp.get('positions');
  if (positionsRaw && positionsRaw.trim()) {
    const parts = positionsRaw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    if (parts.length > 0) {
      draft.scopeMode = 'custom';
      draft.scopePreset = 'all';
      draft.scopeCustomPositions = [...new Set(parts)].sort();
    }
  } else {
    const sc = sp.get('scope') as 'all' | 'apps_or_none' | 'no_alliance' | null;
    if (sc === 'apps_or_none' || sc === 'no_alliance') {
      draft.scopeMode = 'preset';
      draft.scopePreset = sc;
      draft.scopeCustomPositions = [];
    }
  }

  return draft;
}

export function migrateStoredAlliance(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((s) => String(s).trim()).filter(Boolean);
  }
  if (typeof value === 'string' && value.trim()) return [value.trim()];
  return [];
}

/** Merge persisted JSON (possibly legacy shape) into draft field updates. */
export function migrateLegacyRaidsDraftBlob(stored: Record<string, unknown>): Partial<RaidsDraftFilters> {
  const out: Partial<RaidsDraftFilters> = {};

  if (stored.alliance !== undefined) {
    out.alliance = migrateStoredAlliance(stored.alliance);
  }
  if (stored.allianceMode === 'include' || stored.allianceMode === 'exclude') {
    out.allianceMode = stored.allianceMode;
  }
  if (stored.allianceExclude !== undefined) {
    out.allianceExclude = migrateStoredAlliance(stored.allianceExclude);
  }
  if (typeof stored.beige === 'string') {
    out.beige = stored.beige as RaidsDraftFilters['beige'];
  }
  if (typeof stored.maxWars === 'string') {
    out.maxWars = stored.maxWars === '3' ? 'all' : stored.maxWars;
  }
  if (typeof stored.performance === 'boolean') {
    out.performance = stored.performance;
  }
  if (typeof stored.scoreMode === 'string') out.scoreMode = stored.scoreMode;
  if (typeof stored.yourScore === 'string') out.yourScore = stored.yourScore;
  if (typeof stored.minScore === 'string') out.minScore = stored.minScore;
  if (typeof stored.maxScore === 'string') out.maxScore = stored.maxScore;

  if (stored.inactiveMode !== undefined) {
    if (stored.inactiveMode === 'none' || stored.inactiveMode === 'preset' || stored.inactiveMode === 'custom') {
      out.inactiveMode = stored.inactiveMode;
    }
    if (typeof stored.inactivePreset === 'string') out.inactivePreset = stored.inactivePreset;
    if (typeof stored.inactiveCustom === 'string') out.inactiveCustom = stored.inactiveCustom;
  } else if (typeof stored.inactiveMinDays === 'string') {
    if (stored.inactiveMinDays === 'none') {
      out.inactiveMode = 'none';
      out.inactivePreset = '3';
      out.inactiveCustom = '';
    } else if ((INACTIVE_PRESET_DAYS as readonly string[]).includes(stored.inactiveMinDays)) {
      out.inactiveMode = 'preset';
      out.inactivePreset = stored.inactiveMinDays;
      out.inactiveCustom = '';
    } else {
      out.inactiveMode = 'custom';
      out.inactiveCustom = stored.inactiveMinDays;
      out.inactivePreset = '3';
    }
  }

  if (stored.lootMode !== undefined) {
    if (stored.lootMode === 'none' || stored.lootMode === 'preset' || stored.lootMode === 'custom') {
      out.lootMode = stored.lootMode;
    }
    if (typeof stored.lootPreset === 'string') out.lootPreset = stored.lootPreset;
    if (typeof stored.lootCustom === 'string') out.lootCustom = stored.lootCustom;
  } else if (typeof stored.minBeigeLoot === 'string') {
    const c = classifyLootColumnValue(stored.minBeigeLoot);
    out.lootMode = c.lootMode;
    out.lootPreset = c.lootPreset;
    out.lootCustom = c.lootCustom;
  }

  if (stored.scopeMode !== undefined || Array.isArray(stored.scopeCustomPositions)) {
    if (stored.scopeMode === 'preset' || stored.scopeMode === 'custom') {
      out.scopeMode = stored.scopeMode;
    }
    if (typeof stored.scopePreset === 'string') {
      out.scopePreset = stored.scopePreset as RaidsDraftFilters['scopePreset'];
    }
    if (Array.isArray(stored.scopeCustomPositions)) {
      out.scopeCustomPositions = stored.scopeCustomPositions.map((s) => String(s)).filter(Boolean).sort();
    }
  } else if (typeof stored.scope === 'string') {
    if (stored.scope === 'apps_or_none' || stored.scope === 'no_alliance') {
      out.scopeMode = 'preset';
      out.scopePreset = stored.scope as RaidsDraftFilters['scopePreset'];
      out.scopeCustomPositions = [];
    } else if (stored.scope === 'all') {
      out.scopeMode = 'preset';
      out.scopePreset = 'all';
      out.scopeCustomPositions = [];
    }
  }

  return out;
}

/** MRT column filter rows derived from sidebar / URL-backed draft (mapped columns). */
export function buildMappedColumnFiltersFromDraft(d: RaidsDraftFilters): MRT_ColumnFiltersState {
  const filters: MRT_ColumnFiltersState = [];
  if (d.allianceMode === 'include' && d.alliance.length > 0) {
    filters.push({ id: 'allianceName', value: d.alliance });
  }
  if (d.beige === 'only' || d.beige === 'hide') {
    filters.push({ id: 'beigeTurns', value: d.beige });
  }
  if (d.maxWars !== 'all') {
    filters.push({ id: 'defSlots', value: d.maxWars });
  }
  const inactiveMin = effectiveInactiveMinString(d);
  if (inactiveMin) {
    filters.push({ id: 'daysInactive', value: inactiveMin });
  }
  if (d.scopeMode === 'custom' && d.scopeCustomPositions.length > 0) {
    filters.push({ id: 'alliancePosition', value: [...d.scopeCustomPositions] });
  } else if (d.scopeMode === 'preset') {
    if (d.scopePreset === 'apps_or_none') {
      filters.push({ id: 'alliancePosition', value: ['APPLICANT', 'NOALLIANCE'] });
    } else if (d.scopePreset === 'no_alliance') {
      filters.push({ id: 'alliancePosition', value: ['NOALLIANCE'] });
    }
  }
  const lootMinStr = (() => {
    if (d.lootMode === 'preset' && d.lootPreset !== '0') {
      return d.lootPreset;
    }
    if (d.lootMode === 'custom' && d.lootCustom.trim()) {
      return d.lootCustom.trim();
    }
    return '';
  })();
  if (lootMinStr) {
    filters.push({ id: 'nationLoot', value: lootMinStr });
  }
  return filters;
}

export function effectiveInactiveMinString(d: RaidsDraftFilters): string | null {
  if (d.inactiveMode === 'none') return null;
  if (d.inactiveMode === 'preset') return d.inactivePreset;
  const t = d.inactiveCustom.trim();
  return t.length ? t : null;
}

export function effectiveLootMinNumber(d: RaidsDraftFilters): number | undefined {
  if (d.lootMode === 'none' || (d.lootMode === 'preset' && d.lootPreset === '0')) {
    return undefined;
  }
  if (d.lootMode === 'preset') {
    const n = Number(d.lootPreset);
    return Number.isFinite(n) && n > 0 ? n : undefined;
  }
  const n = parseNumericValue(d.lootCustom);
  return n > 0 ? n : undefined;
}

/** Draft keys the page keeps in the URL (Raid Targets' own query string). */
export const RAID_FILTER_URL_KEYS = [
  'alliance',
  'allianceMode',
  'allianceExclude',
  'beige',
  'maxWars',
  'inactiveMinDays',
  'scope',
  'positions',
  'minBeigeLoot',
  'performance',
  'scoreMode',
  'yourScore',
  'minScore',
  'maxScore',
] as const;

/** A score the user or the game gave: finite and above 0; otherwise undefined. */
export function validScore(text: string): number | undefined {
  if (!text.trim()) return undefined;
  const n = Number(text);
  return Number.isFinite(n) && n > 0 ? n : undefined;
}

/** Replace the draft keys in `next` with the URL form of `draft`. */
export function writeRaidsDraftToSearchParams(next: URLSearchParams, draft: RaidsDraftFilters): void {
  RAID_FILTER_URL_KEYS.forEach((key) => next.delete(key));

  if (draft.allianceMode === 'exclude') {
    next.set('allianceMode', 'exclude');
    for (const name of draft.allianceExclude) {
      if (name.trim()) next.append('allianceExclude', name.trim());
    }
  } else {
    for (const name of draft.alliance) {
      if (name.trim()) next.append('alliance', name.trim());
    }
  }

  if (draft.beige === 'only') next.set('beige', 'true');
  else if (draft.beige === 'hide') next.set('beige', 'false');

  if (draft.maxWars !== 'all') next.set('maxWars', draft.maxWars);

  const inactiveMin = effectiveInactiveMinString(draft);
  if (inactiveMin) next.set('inactiveMinDays', inactiveMin);

  if (draft.scopeMode === 'custom' && draft.scopeCustomPositions.length > 0) {
    next.set('positions', draft.scopeCustomPositions.join(','));
  } else if (draft.scopeMode === 'preset' && draft.scopePreset !== 'all') {
    next.set('scope', draft.scopePreset);
  }

  const lootMin = effectiveLootMinNumber(draft);
  if (lootMin !== undefined) next.set('minBeigeLoot', String(Math.round(lootMin)));

  if (draft.performance) next.set('performance', 'true');

  next.set('scoreMode', draft.scoreMode === 'yours' ? 'yours' : 'custom');
  if (draft.scoreMode === 'yours') {
    const score = validScore(draft.yourScore);
    if (score !== undefined) {
      const { minScore, maxScore } = warRangeQueryBounds(score);
      next.set('yourScore', draft.yourScore);
      next.set('minScore', String(minScore));
      next.set('maxScore', String(maxScore));
    }
  } else {
    if (draft.minScore) next.set('minScore', draft.minScore);
    if (draft.maxScore) next.set('maxScore', draft.maxScore);
  }
}

export function allianceNamesFromColumnFilterValue(value: unknown): string[] {
  if (value == null || value === '') return [];
  if (Array.isArray(value)) {
    return value.map((v) => String(v)).filter((s) => s.length > 0);
  }
  return [String(value)];
}

function minNumericKey(value: unknown): string {
  return value == null || value === '' ? '' : String(parseNumericValue(value));
}

/** Whether two values of a mapped column filter mean the same sidebar setting. */
export function mappedFilterValuesEqual(id: string, before: unknown, after: unknown): boolean {
  switch (id) {
    case 'allianceName':
      return (
        JSON.stringify(allianceNamesFromColumnFilterValue(before).sort()) ===
        JSON.stringify(allianceNamesFromColumnFilterValue(after).sort())
      );
    case 'defSlots':
      return normalizeDefSlotsFilterValue(before) === normalizeDefSlotsFilterValue(after);
    case 'daysInactive':
    case 'nationLoot':
      return minNumericKey(before) === minNumericKey(after);
    case 'alliancePosition':
      return (
        positionsArrayKey(Array.isArray(before) ? (before as string[]) : []) ===
        positionsArrayKey(Array.isArray(after) ? (after as string[]) : [])
      );
    case 'beigeTurns':
      return String(before ?? '') === String(after ?? '');
    default:
      return JSON.stringify(before) === JSON.stringify(after);
  }
}

/** The draft with the sidebar settings for `ids` taken from those mapped column filters. */
export function applyMappedColumnFilters(
  prev: RaidsDraftFilters,
  filters: MRT_ColumnFiltersState,
  ids: readonly string[]
): RaidsDraftFilters {
  const valueOf = (id: string) => filters.find((f) => f.id === id)?.value;
  const next: RaidsDraftFilters = { ...prev };
  for (const id of ids) {
    const value = valueOf(id);
    if (id === 'allianceName') {
      next.alliance = allianceNamesFromColumnFilterValue(value);
    } else if (id === 'beigeTurns') {
      next.beige = value === 'only' ? 'only' : value === 'hide' ? 'hide' : 'all';
    } else if (id === 'defSlots') {
      const slots = normalizeDefSlotsFilterValue(value);
      // 3 used slots is the most a nation can have, so "at most 3" means any.
      next.maxWars = slots === '' || slots === '3' ? 'all' : slots;
    } else if (id === 'daysInactive') {
      Object.assign(next, classifyInactiveColumnValue(value));
    } else if (id === 'nationLoot') {
      Object.assign(next, classifyLootColumnValue(value));
    } else if (id === 'alliancePosition') {
      Object.assign(next, classifyAlliancePositionFilter(value));
    }
  }
  return next;
}
