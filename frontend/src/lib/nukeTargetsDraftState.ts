import {
  classifyInactiveColumnValue,
  parseNumericValue,
} from '@/lib/raidFilterParsing';

export type NukeTargetsDraftFilters = {
  allianceMode: 'include' | 'exclude';
  alliance: string[];
  allianceExclude: string[];
  beige: 'all' | 'only' | 'hide';
  maxWars: string;
  inactiveMode: 'none' | 'preset' | 'custom';
  inactivePreset: string;
  inactiveCustom: string;
  minMaxInfra: string;
  minAvgInfra: string;
  hideVds: boolean;
  hideIronDome: boolean;
  sortMode: 'simNuke' | 'simMissile' | 'nukeNet' | 'nukeDamage';
  scoreMode: string;
  yourScore: string;
  minScore: string;
  maxScore: string;
};

export const DEFAULT_NUKE_TARGETS_DRAFT = (
  scoreDefaults: { scoreMode: string; yourScore: string }
): NukeTargetsDraftFilters => ({
  allianceMode: 'include',
  alliance: [],
  allianceExclude: [],
  beige: 'hide',
  maxWars: '2',
  inactiveMode: 'none',
  inactivePreset: '3',
  inactiveCustom: '',
  minMaxInfra: '',
  minAvgInfra: '',
  hideVds: false,
  hideIronDome: false,
  sortMode: 'simNuke',
  scoreMode: scoreDefaults.scoreMode,
  yourScore: scoreDefaults.yourScore,
  minScore: '',
  maxScore: '',
});

function parseAlliances(sp: URLSearchParams, key: 'alliance' | 'allianceExclude'): string[] {
  return [...new Set(sp.getAll(key).map((s) => s.trim()).filter(Boolean))];
}

function parseBooleanParam(sp: URLSearchParams, key: string): boolean | undefined {
  const val = sp.get(key);
  if (val === null) return undefined;
  return val === 'true' || val === '1';
}

export function buildNukeTargetsDraftFromSearchParams(
  sp: URLSearchParams,
  savedNationId: string | undefined,
  nationScore: string
): NukeTargetsDraftFilters {
  const base = DEFAULT_NUKE_TARGETS_DRAFT({
    scoreMode: sp.get('scoreMode') || (savedNationId ? 'yours' : 'custom'),
    yourScore: sp.get('yourScore') || nationScore || '',
  });

  const sortRaw = sp.get('sortMode');
  const sortMode: NukeTargetsDraftFilters['sortMode'] =
    sortRaw === 'simMissile' ||
    sortRaw === 'nukeNet' ||
    sortRaw === 'nukeDamage'
      ? sortRaw
      : 'simNuke';

  const beigeRaw = sp.get('beige');
  const beige: NukeTargetsDraftFilters['beige'] =
    beigeRaw === 'true' || beigeRaw === '1'
      ? 'only'
      : beigeRaw === 'false' || beigeRaw === '0'
        ? 'hide'
        : beigeRaw === 'all'
          ? 'all'
          : base.beige;

  return {
    ...base,
    allianceMode: sp.get('allianceMode') === 'exclude' ? 'exclude' : 'include',
    alliance: parseAlliances(sp, 'alliance'),
    allianceExclude: parseAlliances(sp, 'allianceExclude'),
    beige,
    maxWars: (() => {
      const n = sp.get('maxWars');
      // Missing → page default (2). Explicit "all"/"3" → any wars.
      if (n === null || n === '') return base.maxWars;
      if (n === 'all' || n === '3') return 'all';
      if (['0', '1', '2'].includes(n)) return n;
      return base.maxWars;
    })(),
    minMaxInfra: sp.get('minMaxInfra') || '',
    minAvgInfra: sp.get('minAvgInfra') || '',
    hideVds: parseBooleanParam(sp, 'hideVds') ?? false,
    hideIronDome: parseBooleanParam(sp, 'hideIronDome') ?? false,
    sortMode,
    minScore: sp.get('minScore') || '',
    maxScore: sp.get('maxScore') || '',
    inactiveMode: (() => {
      const raw = sp.get('inactiveMinDays');
      if (raw === null || raw === '') return 'none' as const;
      return classifyInactiveColumnValue(raw).inactiveMode;
    })(),
    inactivePreset: (() => {
      const raw = sp.get('inactiveMinDays');
      if (raw === null || raw === '') return '3';
      return classifyInactiveColumnValue(raw).inactivePreset;
    })(),
    inactiveCustom: (() => {
      const raw = sp.get('inactiveMinDays');
      if (raw === null || raw === '') return '';
      return classifyInactiveColumnValue(raw).inactiveCustom;
    })(),
  };
}

export function effectiveInactiveMinString(d: NukeTargetsDraftFilters): string | undefined {
  if (d.inactiveMode === 'none') return undefined;
  if (d.inactiveMode === 'custom') {
    const n = parseNumericValue(d.inactiveCustom);
    return n > 0 ? String(n) : undefined;
  }
  return d.inactivePreset;
}

export const NUKE_TARGETS_FILTER_STORAGE_KEY = 'autolycus-nuke-targets-filters-v1';

export function serializeNukeTargetsFilters(draft: NukeTargetsDraftFilters): string {
  return JSON.stringify({ v: 1, draft });
}

export function parseNukeTargetsFiltersStorage(
  raw: string | null,
  nationId?: string
): NukeTargetsDraftFilters | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as { v?: number; draft?: Partial<NukeTargetsDraftFilters> };
    if (parsed?.draft && typeof parsed.draft === 'object') {
      return {
        ...DEFAULT_NUKE_TARGETS_DRAFT({
          scoreMode: nationId ? 'yours' : 'custom',
          yourScore: '',
        }),
        ...parsed.draft,
      };
    }
  } catch {
    return null;
  }
  return null;
}
