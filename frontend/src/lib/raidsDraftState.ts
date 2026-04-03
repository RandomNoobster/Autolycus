import {
  classifyInactiveColumnValue,
  classifyLootColumnValue,
  INACTIVE_PRESET_DAYS,
  parseNumericValue,
} from '@/lib/raidFilterParsing';

export type RaidsDraftFilters = {
  alliance: string[];
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
  alliance: [],
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

function parseAlliancesFromSearchParams(sp: URLSearchParams): string[] {
  const raw = sp.getAll('alliance').map((s) => s.trim()).filter(Boolean);
  return [...new Set(raw)];
}

function parseBooleanParam(sp: URLSearchParams, key: string): boolean | undefined {
  const val = sp.get(key);
  if (val === null) return undefined;
  return val === 'true' || val === '1';
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
  const beigeBool = parseBooleanParam(sp, 'beige');
  const base = DEFAULT_RAIDS_DRAFT_FILTERS({
    scoreMode: sp.get('scoreMode') || (savedNationId ? 'yours' : 'custom'),
    yourScore: sp.get('yourScore') || nationScore || '',
  });

  const draft: RaidsDraftFilters = {
    ...base,
    alliance: parseAlliancesFromSearchParams(sp),
    beige: beigeBool === true ? 'only' : beigeBool === false ? 'hide' : 'all',
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
      .map((s) => decodeURIComponent(s.trim()))
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
