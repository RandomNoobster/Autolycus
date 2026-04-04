/**
 * Raids Page
 *
 * Displays raid targets with Discord OAuth web sessions.
 */

import {
  Box,
  Container,
  Title,
  Text,
  Stack,
  Group,
  Badge,
  Paper,
  Grid,
  NumberInput,
  Select,
  Switch,
  Button,
  MultiSelect,
  Anchor,
  Alert,
  Loader,
  Skeleton,
  TextInput,
} from '@mantine/core';
import { useState, useCallback, useMemo, useEffect, useLayoutEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { IconX, IconBrandDiscord, IconDownload, IconInfoCircle } from '@tabler/icons-react';
import type {
  MRT_ColumnFiltersState,
  MRT_ColumnOrderState,
  MRT_DensityState,
  MRT_VisibilityState,
} from 'mantine-react-table';

import { fetchRaids } from '@/api';
import { getDiscordLoginUrl, getLinkedNation } from '@/api/auth';
import {
  useUrlParams,
  useNationId,
  useTablePersistence,
  useRaidsSearchParams,
} from '@/hooks';
import { RaidsTable } from '@/components/raids';
import { ErrorState, NationIdField, VerifyNationModal } from '@/components/common';
import type { ApiError } from '@/types';
import {
  parseNumericValue,
  positionsArrayKey,
  defSlotsFilterCompareKey,
  classifyAlliancePositionFilter,
  classifyInactiveColumnValue,
  classifyLootColumnValue,
} from '@/lib/raidFilterParsing';
import type { RaidsDraftFilters } from '@/lib/raidsDraftState';
import {
  DEFAULT_RAIDS_DRAFT_FILTERS,
  buildRaidsDraftFromSearchParams,
  buildMappedColumnFiltersFromDraft,
  migrateLegacyRaidsDraftBlob,
  migrateStoredAlliance,
  effectiveInactiveMinString,
  effectiveLootMinNumber,
} from '@/lib/raidsDraftState';
import {
  RAIDS_FILTERS_LOCAL_STORAGE_KEY,
  RAIDS_MAPPED_FILTER_COLUMN_IDS,
  parseRaidsFiltersStorageJson,
  serializeRaidsFiltersStorageV2,
} from '@/lib/raidsFiltersStorage';

type TableSettings = {
  columnVisibility: MRT_VisibilityState;
  columnOrder: MRT_ColumnOrderState;
  density: MRT_DensityState;
  columnFilters: MRT_ColumnFiltersState;
};

const DEFAULT_TABLE_SETTINGS: TableSettings = {
  columnVisibility: {
    id: true,
    nationName: true,
    leaderName: true,
    allianceName: true,
    alliancePosition: true,
    numCities: true,
    color: true,
    beigeTurns: true,
    reminder: true,
    nationLoot: true,
    daysInactive: true,
    updatedAt: true,
    monetaryNetIncome: true,
    netCashIncome: true,
    taxable: true,
    treasures: true,
    defSlots: true,
    timeSinceWar: true,
    soldiers: true,
    tanks: true,
    aircraft: true,
    ships: true,
    missiles: true,
    nukes: true,
    groundWin: true,
    airWin: true,
    navalWin: true,
    totalWin: true,
  },
  columnOrder: [
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
    'mrt-row-spacer',
  ],
  density: 'xs',
  columnFilters: [],
};

const RAIDS_TABLE_PERSISTENCE_DEFAULTS = {
  columnVisibility: DEFAULT_TABLE_SETTINGS.columnVisibility,
  columnOrder: DEFAULT_TABLE_SETTINGS.columnOrder,
  density: DEFAULT_TABLE_SETTINGS.density,
};

const MAPPED_COLUMN_IDS = RAIDS_MAPPED_FILTER_COLUMN_IDS;


function mergeColumnFilters(
  base: MRT_ColumnFiltersState,
  overrides: MRT_ColumnFiltersState
): MRT_ColumnFiltersState {
  const map = new Map<string, any>();
  base.forEach((f) => map.set(f.id, f.value));
  overrides.forEach((f) => map.set(f.id, f.value));
  return Array.from(map.entries()).map(([id, value]) => ({ id, value }));
}

function allianceNamesFromColumnFilterValue(value: unknown): string[] {
  if (value == null || value === '') return [];
  if (Array.isArray(value)) {
    return value.map((v) => String(v)).filter((s) => s.length > 0);
  }
  return [String(value)];
}

function parseAlliancesFromSearchParams(sp: URLSearchParams): string[] {
  const raw = sp.getAll('alliance').map((s) => s.trim()).filter(Boolean);
  return [...new Set(raw)];
}

const RAID_FILTER_URL_KEYS = [
  'alliance',
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

export function RaidsPage() {
  const { columnFiltersFromUrl, initialSorting } = useUrlParams();
  const { nationId: savedNationId, parseNationId, setNationId } = useNationId();
  const [searchParams, setSearchParams] = useRaidsSearchParams();

  const targetNationIds = searchParams.get('targetNationIds') || undefined;
  const attackerNationIdParam = searchParams.get('attackerNationId') || undefined;
  const useSavedTargets = searchParams.get('useSavedTargets') === 'true';
  const { data: linkedNationData, refetch: refetchLinkedNation } = useQuery({
    queryKey: ['linkedNation'],
    queryFn: async () => {
      try {
        return await getLinkedNation();
      } catch {
        return null;
      }
    },
    retry: false,
  });
  const linkedNationId = linkedNationData?.linked ? linkedNationData.nation_id || undefined : undefined;
  const resolvedNationId = attackerNationIdParam || linkedNationId || savedNationId;
  const [appliedNationId, setAppliedNationId] = useState(resolvedNationId);
  const [draftNationId, setDraftNationId] = useState(resolvedNationId);
  const [verifyModalOpen, setVerifyModalOpen] = useState(false);

  useEffect(() => {
    const nextNationId = attackerNationIdParam || linkedNationId || savedNationId;
    if (nextNationId && nextNationId !== appliedNationId) {
      setAppliedNationId(nextNationId);
      setDraftNationId(nextNationId);
    }
    if (attackerNationIdParam) {
      const parsed = parseNationId(attackerNationIdParam);
      if (parsed) {
        setNationId(parsed);
      }
    }
  }, [attackerNationIdParam, linkedNationId, savedNationId, appliedNationId, parseNationId, setNationId]);

  const parseNumber = (key: string): number | undefined => {
    const val = searchParams.get(key);
    if (val === null || val === '') return undefined;
    const num = Number(val);
    return Number.isNaN(num) ? undefined : num;
  };

  const parseBoolean = (key: string): boolean | undefined => {
    const val = searchParams.get(key);
    if (val === null) return undefined;
    return val === 'true' || val === '1';
  };

  // Active filters from URL (drives filteredTargets; kept in sync with draft via effect below)
  const activeFilters = useMemo(() => {
    const positionsRaw = searchParams.get('positions');
    const positionFilter =
      positionsRaw && positionsRaw.trim()
        ? positionsRaw
            .split(',')
            .map((s) => decodeURIComponent(s.trim()))
            .filter(Boolean)
        : [];
    const maxWarsRaw = parseNumber('maxWars');
    return {
      alliance: parseAlliancesFromSearchParams(searchParams),
      beige: parseBoolean('beige'),
      // 3 in the URL is legacy "any" (same as omitting maxWars); draft maps it to 'all'.
      maxWars: maxWarsRaw === 3 ? undefined : maxWarsRaw,
      inactiveMinDays: parseNumber('inactiveMinDays'),
      scope: (searchParams.get('scope') as 'all' | 'apps_or_none' | 'no_alliance' | null) || undefined,
      positionFilter: positionFilter.length > 0 ? positionFilter : undefined,
      minBeigeLoot: parseNumber('minBeigeLoot'),
      performance: parseBoolean('performance'),
      scoreMode: searchParams.get('scoreMode') || 'custom',
      yourScore: parseNumber('yourScore'),
      minScore: parseNumber('minScore'),
      maxScore: parseNumber('maxScore'),
    };
  }, [searchParams]);

  const [draftFilters, setDraftFilters] = useState<RaidsDraftFilters>(() =>
    buildRaidsDraftFromSearchParams(searchParams, savedNationId, '')
  );

  const {
    columnVisibility,
    setColumnVisibility,
    columnOrder,
    setColumnOrder,
  } = useTablePersistence('raids', RAIDS_TABLE_PERSISTENCE_DEFAULTS);

  const [columnFilters, setColumnFilters] = useState<MRT_ColumnFiltersState>(
    () => [...DEFAULT_TABLE_SETTINGS.columnFilters]
  );
  const prevColumnFiltersRef = useRef<MRT_ColumnFiltersState>(
    DEFAULT_TABLE_SETTINGS.columnFilters
  );
  const syncingFromFiltersRef = useRef(false);
  const filtersRestoredRef = useRef(false);
  /**
   * After hydrating from localStorage, draft URL sync + persist effects must not run in the same
   * passive effect pass as the restore: they would still see the pre-restore draft/columnFilters and
   * overwrite the URL, table filters, and localStorage with defaults.
   */
  const suppressDraftUrlSyncAndPersistRef = useRef(false);
  const searchParamsKey = useMemo(() => searchParams.toString(), [searchParams]);

  useLayoutEffect(() => {
    suppressDraftUrlSyncAndPersistRef.current = false;
  });

  // Fetch raids data - must be before any conditional returns
  const {
    data,
    isLoading,
    isFetching,
    error,
    refetch,
  } = useQuery({
    queryKey: ['raids', appliedNationId, targetNationIds, useSavedTargets],
    queryFn: () => {
      const filters: any = { minScore: 15, vmode: false };
      if (appliedNationId) {
        filters.attackerNationId = parseInt(appliedNationId, 10);
      }
      if (targetNationIds) {
        filters.targetNationIds = targetNationIds;
      }
      if (useSavedTargets) {
        filters.useSavedTargets = true;
      }
      return fetchRaids(filters);
    },
    retry: false,
  });

  /** Same option list for sidebar MultiSelect and table column (full API list + current picks). */
  const allianceFilterOptions = useMemo(() => {
    const names = new Set<string>();
    for (const t of data?.targets ?? []) {
      const a = t.allianceName;
      if (a && a !== 'None') names.add(a);
    }
    for (const a of draftFilters.alliance) {
      if (a.trim()) names.add(a.trim());
    }
    return Array.from(names).sort((a, b) => a.localeCompare(b));
  }, [data?.targets, draftFilters.alliance]);

  const positionFilterOptions = useMemo(() => {
    const positions = new Set<string>();
    for (const t of data?.targets ?? []) {
      const p = t.alliancePosition;
      if (p) positions.add(p);
    }
    for (const p of draftFilters.scopeCustomPositions) {
      if (p) positions.add(p);
    }
    const posCol = columnFilters.find((f) => f.id === 'alliancePosition')?.value;
    if (Array.isArray(posCol)) {
      for (const p of posCol) {
        if (p) positions.add(String(p));
      }
    }
    return Array.from(positions)
      .map((p) => ({
        value: p,
        label: p === 'NOALLIANCE' ? 'None' : p.toLowerCase(),
      }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [data?.targets, draftFilters.scopeCustomPositions, columnFilters]);

  useEffect(() => {
    if (filtersRestoredRef.current) return;
    const hasUrlFilters = RAID_FILTER_URL_KEYS.some((key) => {
      if (key === 'alliance') return searchParams.getAll('alliance').some(Boolean);
      return searchParams.get(key) !== null;
    });
    if (hasUrlFilters) {
      filtersRestoredRef.current = true;
      return;
    }

    try {
      const raw = localStorage.getItem(RAIDS_FILTERS_LOCAL_STORAGE_KEY);
      if (!raw) {
        filtersRestoredRef.current = true;
        return;
      }
      const parsedRoot = JSON.parse(raw) as unknown;
      const storageParsed = parseRaidsFiltersStorageJson(parsedRoot);
      if (!storageParsed) {
        filtersRestoredRef.current = true;
        return;
      }
      const { draftRecord, extras } = storageParsed;
      const migrated = migrateLegacyRaidsDraftBlob(draftRecord);
      if (draftRecord.alliance !== undefined) {
        migrated.alliance = migrateStoredAlliance(draftRecord.alliance);
      }
      const merged: RaidsDraftFilters = {
        ...buildRaidsDraftFromSearchParams(searchParams, savedNationId, ''),
        ...migrated,
      };
      const mapped = buildMappedColumnFiltersFromDraft(merged);
      suppressDraftUrlSyncAndPersistRef.current = true;
      syncingFromFiltersRef.current = true;
      setColumnFilters([...mapped, ...extras]);
      setDraftFilters(merged);

      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        RAID_FILTER_URL_KEYS.forEach((key) => next.delete(key));
        for (const a of merged.alliance) {
          if (a.trim()) next.append('alliance', a.trim());
        }
        if (merged.beige === 'only') next.set('beige', 'true');
        else if (merged.beige === 'hide') next.set('beige', 'false');
        if (merged.maxWars !== 'all') next.set('maxWars', merged.maxWars);
        const inactiveMin = effectiveInactiveMinString(merged);
        if (inactiveMin) next.set('inactiveMinDays', inactiveMin);
        if (merged.scopeMode === 'custom' && merged.scopeCustomPositions.length > 0) {
          next.set('positions', merged.scopeCustomPositions.map((p) => encodeURIComponent(p)).join(','));
        } else if (merged.scopeMode === 'preset' && merged.scopePreset !== 'all') {
          next.set('scope', merged.scopePreset);
        }
        const lootMin = effectiveLootMinNumber(merged);
        if (lootMin !== undefined) next.set('minBeigeLoot', String(Math.round(lootMin)));
        if (merged.performance) next.set('performance', 'true');
        if (merged.scoreMode) next.set('scoreMode', merged.scoreMode);
        if (merged.yourScore) next.set('yourScore', merged.yourScore);
        if (merged.minScore) next.set('minScore', merged.minScore);
        if (merged.maxScore) next.set('maxScore', merged.maxScore);
        return next;
      }, { replace: true });
    } catch (error) {
      console.warn('Failed to restore raids filters', error);
    } finally {
      filtersRestoredRef.current = true;
    }
  }, [searchParams, setSearchParams]);

  // Auto-fill score when attacker data loads and we have a nation ID
  useEffect(() => {
    if (data?.attacker?.score && appliedNationId) {
      const s = data.attacker.score.toString();
      setDraftFilters((prev) => {
        if (prev.scoreMode === 'yours' && prev.yourScore === s) return prev;
        return { ...prev, yourScore: s, scoreMode: 'yours' };
      });
    } else if (!appliedNationId) {
      setDraftFilters((prev) => {
        if (prev.scoreMode !== 'yours') return prev;
        return { ...prev, scoreMode: 'custom' };
      });
    }
  }, [data?.attacker?.score, appliedNationId]);

  // Sync draftNationId with savedNationId when it changes
  useEffect(() => {
    if (savedNationId && !appliedNationId) {
      setAppliedNationId(savedNationId);
      setDraftNationId(savedNationId);
    }
  }, [savedNationId, appliedNationId]);

  useEffect(() => {
    if (!filtersRestoredRef.current) return;
    if (!columnFiltersFromUrl.length) return;
    syncingFromFiltersRef.current = true;
    setColumnFilters((prev) => mergeColumnFilters(prev, columnFiltersFromUrl));
  }, [searchParamsKey, columnFiltersFromUrl]);

  // Sync draft filters when column filters change from table interaction (URL follows draft effect).
  useEffect(() => {
    const previousFilters = prevColumnFiltersRef.current;
    prevColumnFiltersRef.current = columnFilters;

    if (syncingFromFiltersRef.current) {
      syncingFromFiltersRef.current = false;
      return;
    }

    const allianceCompareKey = (val: unknown) =>
      JSON.stringify([...allianceNamesFromColumnFilterValue(val)].sort());

    const minNumericColKey = (val: unknown) =>
      val == null || val === '' ? '' : String(parseNumericValue(val));

    const getVal = (filters: MRT_ColumnFiltersState, id: string) =>
      filters.find((f) => f.id === id)?.value;

    const mappedValuesEqual = (id: string, before: unknown, after: unknown): boolean => {
      if (id === 'allianceName') return allianceCompareKey(before) === allianceCompareKey(after);
      if (id === 'defSlots') return defSlotsFilterCompareKey(before) === defSlotsFilterCompareKey(after);
      if (id === 'daysInactive') return minNumericColKey(before) === minNumericColKey(after);
      if (id === 'nationLoot') return minNumericColKey(before) === minNumericColKey(after);
      if (id === 'alliancePosition') {
        return positionsArrayKey(
          Array.isArray(before) ? (before as string[]) : []
        ) === positionsArrayKey(Array.isArray(after) ? (after as string[]) : []);
      }
      if (id === 'beigeTurns') return String(before ?? '') === String(after ?? '');
      return JSON.stringify(before) === JSON.stringify(after);
    };

    const changedIds: string[] = [];
    MAPPED_COLUMN_IDS.forEach((id) => {
      const before = getVal(previousFilters, id);
      const after = getVal(columnFilters, id);
      if (mappedValuesEqual(id, before, after)) return;
      changedIds.push(id);
    });

    if (!changedIds.length) return;

    setDraftFilters((prev) => {
      const next: RaidsDraftFilters = { ...prev };
      if (changedIds.includes('allianceName')) {
        next.alliance = allianceNamesFromColumnFilterValue(
          columnFilters.find((f) => f.id === 'allianceName')?.value
        );
      }
      if (changedIds.includes('beigeTurns')) {
        const v = getVal(columnFilters, 'beigeTurns');
        next.beige = v === 'only' ? 'only' : v === 'hide' ? 'hide' : 'all';
      }
      if (changedIds.includes('defSlots')) {
        const s = defSlotsFilterCompareKey(getVal(columnFilters, 'defSlots'));
        if (s === '' || s === '3') {
          next.maxWars = 'all';
        } else {
          next.maxWars = s;
        }
      }
      if (changedIds.includes('daysInactive')) {
        const c = classifyInactiveColumnValue(getVal(columnFilters, 'daysInactive'));
        next.inactiveMode = c.inactiveMode;
        next.inactivePreset = c.inactivePreset;
        next.inactiveCustom = c.inactiveCustom;
      }
      if (changedIds.includes('nationLoot')) {
        const c = classifyLootColumnValue(getVal(columnFilters, 'nationLoot'));
        next.lootMode = c.lootMode;
        next.lootPreset = c.lootPreset;
        next.lootCustom = c.lootCustom;
      }
      if (changedIds.includes('alliancePosition')) {
        const c = classifyAlliancePositionFilter(getVal(columnFilters, 'alliancePosition'));
        next.scopeMode = c.scopeMode;
        next.scopePreset = c.scopePreset;
        next.scopeCustomPositions = c.scopeCustomPositions;
      }
      return next;
    });
  }, [columnFilters]);

  // Apply filters locally in the browser - must be before conditional returns
  const filteredTargets = useMemo(() => {
    if (!data?.targets) return [];
    
    let filtered = [...data.targets];

    // Alliance filter (exact names, same as table multi-select)
    if (activeFilters.alliance.length > 0) {
      const allow = new Set(activeFilters.alliance.map((a) => a.toLowerCase()));
      filtered = filtered.filter((nation) => allow.has(nation.allianceName.toLowerCase()));
    }

    // Beige filter
    if (activeFilters.beige === true) {
      filtered = filtered.filter(nation => nation.beigeTurns > 0);
    } else if (activeFilters.beige === false) {
      filtered = filtered.filter(nation => nation.beigeTurns <= 0);
    }

    // Max wars (defSlots = used defensive war count from API)
    if (activeFilters.maxWars !== undefined) {
      filtered = filtered.filter((nation) => nation.defSlots <= activeFilters.maxWars!);
    }

    // Inactivity filter
    if (activeFilters.inactiveMinDays !== undefined) {
      filtered = filtered.filter((nation) => nation.daysInactive >= activeFilters.inactiveMinDays!);
    }

    // Alliance position: custom multi-select from URL `positions` takes precedence over preset `scope`
    if (activeFilters.positionFilter?.length) {
      const allow = new Set(activeFilters.positionFilter);
      filtered = filtered.filter((nation) => allow.has(nation.alliancePosition));
    } else if (activeFilters.scope === 'apps_or_none') {
      filtered = filtered.filter(
        (nation) =>
          nation.alliancePosition === 'NOALLIANCE' || nation.alliancePosition === 'APPLICANT'
      );
    } else if (activeFilters.scope === 'no_alliance') {
      filtered = filtered.filter((nation) => nation.allianceId === '0');
    }

    // Min beige loot filter (using nationLoot)
    if (activeFilters.minBeigeLoot !== undefined && activeFilters.minBeigeLoot > 0) {
      filtered = filtered.filter(nation => {
        const loot = parseFloat(nation.nationLoot.replace(/[^0-9.-]/g, ''));
        return loot >= activeFilters.minBeigeLoot!;
      });
    }

    // Score filter (calculate from cities - rough approximation)
    if (activeFilters.minScore !== undefined || activeFilters.maxScore !== undefined) {
      filtered = filtered.filter(nation => {
        const approxScore = nation.numCities * 150; // Rough estimate
        if (activeFilters.minScore !== undefined && approxScore < activeFilters.minScore) {
          return false;
        }
        if (activeFilters.maxScore !== undefined && approxScore > activeFilters.maxScore) {
          return false;
        }
        return true;
      });
    }

    // Performance filter
    if (activeFilters.performance) {
      filtered = filtered.filter((nation) => {
        const loot = parseFloat(nation.nationLoot.replace(/[^0-9.-]/g, ''));
        return (
          nation.groundWin >= 40 &&
          nation.monetaryNetIncome > 0 &&
          loot > 0
        );
      });
    }

    return filtered;
  }, [data?.targets, activeFilters]);

  const mappedColumnFiltersFromDraft = useCallback(
    (): MRT_ColumnFiltersState => buildMappedColumnFiltersFromDraft(draftFilters),
    [draftFilters]
  );

  const syncColumnFiltersFromDraft = useCallback(() => {
    const mapped = mappedColumnFiltersFromDraft();
    syncingFromFiltersRef.current = true;
    setColumnFilters((prev) => {
      const preserved = prev.filter((f) => !MAPPED_COLUMN_IDS.has(f.id));
      return [...preserved, ...mapped];
    });
  }, [mappedColumnFiltersFromDraft]);

  const syncColumnFiltersFromDraftRef = useRef(syncColumnFiltersFromDraft);
  syncColumnFiltersFromDraftRef.current = syncColumnFiltersFromDraft;

  const resetFilters = useCallback(() => {
    const nationScore = data?.attacker?.score?.toString() || '';
    setDraftFilters(
      DEFAULT_RAIDS_DRAFT_FILTERS({
        scoreMode: appliedNationId ? 'yours' : 'custom',
        yourScore: nationScore,
      })
    );
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      RAID_FILTER_URL_KEYS.forEach((k) => next.delete(k));
      return next;
    }, { replace: true });
    syncingFromFiltersRef.current = true;
    setColumnFilters((prev) => prev.filter((f) => !MAPPED_COLUMN_IDS.has(f.id)));
    try {
      localStorage.removeItem(RAIDS_FILTERS_LOCAL_STORAGE_KEY);
    } catch (error) {
      console.warn('Failed to clear raids filter storage', error);
    }
  }, [setSearchParams, data?.attacker?.score, appliedNationId]);

  // Keep URL + localStorage in sync with draft UI (no debounce — debounced URL lag caused scoreMode query to fight the visible filters).
  useEffect(() => {
    if (!filtersRestoredRef.current) return;
    if (suppressDraftUrlSyncAndPersistRef.current) return;

    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      const preservedScore = {
        scoreMode: next.get('scoreMode'),
        yourScore: next.get('yourScore'),
        minScore: next.get('minScore'),
        maxScore: next.get('maxScore'),
      };

      RAID_FILTER_URL_KEYS.forEach((k) => next.delete(k));

      for (const a of draftFilters.alliance) {
        if (a.trim()) next.append('alliance', a.trim());
      }

      if (draftFilters.beige === 'only') next.set('beige', 'true');
      else if (draftFilters.beige === 'hide') next.set('beige', 'false');

      if (draftFilters.maxWars !== 'all') next.set('maxWars', draftFilters.maxWars);

      const inactiveMin = effectiveInactiveMinString(draftFilters);
      if (inactiveMin) next.set('inactiveMinDays', inactiveMin);

      if (draftFilters.scopeMode === 'custom' && draftFilters.scopeCustomPositions.length > 0) {
        next.set(
          'positions',
          draftFilters.scopeCustomPositions.map((p) => encodeURIComponent(p)).join(',')
        );
      } else if (draftFilters.scopeMode === 'preset' && draftFilters.scopePreset !== 'all') {
        next.set('scope', draftFilters.scopePreset);
      }

      const lootNum = effectiveLootMinNumber(draftFilters);
      if (lootNum !== undefined) next.set('minBeigeLoot', String(Math.round(lootNum)));

      if (draftFilters.performance) next.set('performance', 'true');

      // Score handling
      if (draftFilters.scoreMode === 'yours' && draftFilters.yourScore) {
        const score = Number(draftFilters.yourScore);
        if (!Number.isNaN(score)) {
          next.set('minScore', String(Math.round(score * 0.75)));
          next.set('maxScore', String(Math.round(score * 2.5)));
          next.set('scoreMode', 'yours');
          next.set('yourScore', draftFilters.yourScore);
        } else if (preservedScore.scoreMode === 'yours' && preservedScore.yourScore) {
          if (preservedScore.minScore) next.set('minScore', preservedScore.minScore);
          if (preservedScore.maxScore) next.set('maxScore', preservedScore.maxScore);
          next.set('scoreMode', preservedScore.scoreMode);
          next.set('yourScore', preservedScore.yourScore);
        }
      } else if (draftFilters.scoreMode === 'yours') {
        // "Yours" but empty score (e.g. NumberInput flicker): keep URL stable
        if (preservedScore.scoreMode === 'yours' && preservedScore.yourScore) {
          if (preservedScore.minScore) next.set('minScore', preservedScore.minScore);
          if (preservedScore.maxScore) next.set('maxScore', preservedScore.maxScore);
          next.set('scoreMode', preservedScore.scoreMode);
          next.set('yourScore', preservedScore.yourScore);
        }
      } else if (draftFilters.scoreMode === 'custom') {
        if (draftFilters.minScore) next.set('minScore', draftFilters.minScore);
        if (draftFilters.maxScore) next.set('maxScore', draftFilters.maxScore);
        next.set('scoreMode', 'custom');
      }

      if (next.toString() === prev.toString()) return prev;
      return next;
    }, { replace: true });

    syncColumnFiltersFromDraftRef.current();
  }, [draftFilters, setSearchParams]);

  useEffect(() => {
    if (!filtersRestoredRef.current) return;
    if (suppressDraftUrlSyncAndPersistRef.current) return;
    try {
      localStorage.setItem(
        RAIDS_FILTERS_LOCAL_STORAGE_KEY,
        serializeRaidsFiltersStorageV2(draftFilters, columnFilters)
      );
    } catch (error) {
      console.warn('Failed to persist raids filters', error);
    }
  }, [draftFilters, columnFilters]);

  type ColumnFiltersUpdater = MRT_ColumnFiltersState | ((prev: MRT_ColumnFiltersState) => MRT_ColumnFiltersState);

  const handleColumnFiltersChange = useCallback((updater: ColumnFiltersUpdater) => {
    setColumnFilters((prevFilters) =>
      typeof updater === 'function' ? updater(prevFilters) : updater
    );
  }, []);

  // Conditional returns AFTER all hooks

  if (error) {
    const apiError = error as unknown as ApiError;

    return (
      <ErrorState
        title="Failed to load raids"
        message={apiError.message || 'An unexpected error occurred'}
        onRetry={() => refetch()}
      />
    );
  }

  if (!data && !isLoading) {
    return <ErrorState title="No data" message="No raid data available" />;
  }

  const isInitialLoading = isLoading && !data;
  const discordAuthenticated = data?.discordAuthenticated ?? false;
  const discordLinked = data?.discordLinked ?? false;

  return (
    <Container size="xl" py="md">
      <Stack gap="md">
        {/* Nation Configuration */}
        <Paper withBorder radius="md" p="lg" style={{ position: 'relative' }}>
          <Stack gap="xs">
            <Group gap="xs">
              <Title order={3}>Your Nation</Title>
              <Badge color="blue" variant="light">Optional</Badge>
            </Group>
            <Text size="sm" c="dimmed">
              Load your nation to pull your score automatically and keep the win% + score range aligned to you.
            </Text>
          </Stack>

          <NationIdField
            label="Nation ID"
            placeholder="Nation ID or Link to Nation"
            size="sm"
            value={draftNationId || ''}
            onChange={setDraftNationId}
            onSubmit={() => {
              const parsed = parseNationId(draftNationId);
              if (parsed) {
                setAppliedNationId(parsed);
                setDraftNationId(parsed);
              }
            }}
            buttonLabel="Load Nation"
            buttonIcon={<IconDownload size={14} />}
            buttonDisabled={!draftNationId || draftNationId === appliedNationId}
            loading={isLoading && !!appliedNationId}
            inputProps={{ style: { maxWidth: 260 } }}
            warningMessage={data?.warning || null}
          />
          {linkedNationId && appliedNationId && appliedNationId !== linkedNationId && (
            <Alert color="yellow" variant="light" title="Temporary Override" mt="sm">
              You are currently overriding your linked nation ({linkedNationId}) for this page.
            </Alert>
          )}
          
          {data?.attacker && appliedNationId && !isLoading && (
            <Group gap="xs" style={{ position: 'absolute', top: 16, right: 16 }}>
              <Text size="sm" c="dimmed">
                {data.attacker.nation_name}
              </Text>
              <Badge variant="light" color="blue">
                Score: {data.attacker.score?.toFixed(2) || 'N/A'}
              </Badge>
            </Group>
          )}
        </Paper>

        <Paper withBorder radius="md" p="lg">
          <Stack gap="sm">
            <Stack gap={4}>
              <Title order={3}>Raid Filters</Title>
              <Text size="sm" c="dimmed">
                Adjust the filters below to refine your raid target list.
              </Text>
            </Stack>
            <Grid gutter={{ base: 'sm', sm: 'md' }}>
              <Grid.Col span={{ base: 12, sm: 6, md: 4, lg: 4 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap={6}>
                    <Group gap="xs" justify="space-between">
                      <Text size="sm" fw={600}>Beige Status</Text>
                      {draftFilters.beige !== 'all' && (
                        <Anchor size="xs" onClick={() => setDraftFilters(prev => ({ ...prev, beige: 'all' }))}>
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">Choose whether to include beige nations.</Text>
                    <Select
                      size="sm"
                      data={[
                        { value: 'all', label: 'Show all nations' },
                        { value: 'only', label: 'Only beige nations' },
                        { value: 'hide', label: 'Hide beige nations' },
                      ]}
                      value={draftFilters.beige}
                      onChange={(val) =>
                        setDraftFilters((prev) => ({
                          ...prev,
                          beige: (val || 'all') as RaidsDraftFilters['beige'],
                        }))
                      }
                    />
                  </Stack>
                </Paper>
              </Grid.Col>

              <Grid.Col span={{ base: 12, sm: 6, md: 4, lg: 4 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap={6}>
                    <Group gap="xs" justify="space-between">
                      <Text size="sm" fw={600}>Alliance Name</Text>
                      {draftFilters.alliance.length > 0 && (
                        <Anchor size="xs" onClick={() => setDraftFilters((prev) => ({ ...prev, alliance: [] }))}>
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">Same list as the table column — pick one or more alliances.</Text>
                    <MultiSelect
                      size="sm"
                      placeholder="Select alliances"
                      data={allianceFilterOptions}
                      value={draftFilters.alliance}
                      onChange={(val) => setDraftFilters((prev) => ({ ...prev, alliance: val }))}
                      searchable
                      clearable
                      hidePickedOptions
                      maxDropdownHeight={280}
                    />
                  </Stack>
                </Paper>
              </Grid.Col>

              <Grid.Col span={{ base: 12, sm: 6, md: 4, lg: 4 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap={6}>
                    <Group gap="xs" justify="space-between">
                      <Text size="sm" fw={600}>Alliance Membership</Text>
                      {(draftFilters.scopeMode === 'custom'
                        ? draftFilters.scopeCustomPositions.length > 0
                        : draftFilters.scopePreset !== 'all') && (
                        <Anchor
                          size="xs"
                          onClick={() =>
                            setDraftFilters((prev) => ({
                              ...prev,
                              scopeMode: 'preset',
                              scopePreset: 'all',
                              scopeCustomPositions: [],
                            }))
                          }
                        >
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">Presets match the table, or pick custom positions.</Text>
                    <Select
                      size="sm"
                      data={[
                        { value: 'all', label: 'All nations' },
                        { value: 'apps_or_none', label: 'Applicants + No alliance' },
                        { value: 'no_alliance', label: 'No alliance only' },
                        { value: 'custom', label: 'Custom positions' },
                      ]}
                      value={
                        draftFilters.scopeMode === 'custom' ? 'custom' : draftFilters.scopePreset
                      }
                      onChange={(val) => {
                        if (!val || val === 'all') {
                          setDraftFilters((prev) => ({
                            ...prev,
                            scopeMode: 'preset',
                            scopePreset: 'all',
                            scopeCustomPositions: [],
                          }));
                        } else if (val === 'custom') {
                          setDraftFilters((prev) => ({
                            ...prev,
                            scopeMode: 'custom',
                            scopePreset: 'all',
                            scopeCustomPositions: prev.scopeCustomPositions,
                          }));
                        } else {
                          setDraftFilters((prev) => ({
                            ...prev,
                            scopeMode: 'preset',
                            scopePreset: val as 'apps_or_none' | 'no_alliance',
                            scopeCustomPositions: [],
                          }));
                        }
                      }}
                    />
                    {draftFilters.scopeMode === 'custom' && (
                      <MultiSelect
                        size="sm"
                        placeholder="Positions (same as table column)"
                        data={positionFilterOptions}
                        value={draftFilters.scopeCustomPositions}
                        onChange={(val) =>
                          setDraftFilters((prev) => ({ ...prev, scopeCustomPositions: val }))
                        }
                        searchable
                        clearable
                        hidePickedOptions
                        maxDropdownHeight={280}
                      />
                    )}
                  </Stack>
                </Paper>
              </Grid.Col>

              <Grid.Col span={{ base: 12, sm: 6, md: 4, lg: 4 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap={6}>
                    <Group gap="xs" justify="space-between">
                      <Text size="sm" fw={600}>Defensive Wars</Text>
                      {draftFilters.maxWars !== 'all' && (
                        <Anchor size="xs" onClick={() => setDraftFilters(prev => ({ ...prev, maxWars: 'all' }))}>
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">Upper bound on current defensive wars.</Text>
                    <Group gap="xs" align="center" wrap="nowrap">
                      <Select
                        size="sm"
                        style={{ flex: 1, minWidth: 120 }}
                        data={[
                          { value: 'all', label: 'Any' },
                          { value: '0', label: '0' },
                          { value: '1', label: '1' },
                          { value: '2', label: '2' },
                        ]}
                        value={draftFilters.maxWars}
                        onChange={(val) => setDraftFilters(prev => ({ ...prev, maxWars: val || 'all' }))}
                      />
                      <Text size="sm" c="dimmed">
                        active wars
                      </Text>
                    </Group>
                  </Stack>
                </Paper>
              </Grid.Col>

              <Grid.Col span={{ base: 12, sm: 6, md: 4, lg: 4 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap={6}>
                    <Group gap="xs" justify="space-between">
                      <Text size="sm" fw={600}>Inactivity</Text>
                      {draftFilters.inactiveMode !== 'none' && (
                        <Anchor
                          size="xs"
                          onClick={() =>
                            setDraftFilters((prev) => ({
                              ...prev,
                              inactiveMode: 'none',
                              inactivePreset: '3',
                              inactiveCustom: '',
                            }))
                          }
                        >
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">Presets or a custom minimum (same as table column).</Text>
                    <Select
                      size="sm"
                      data={[
                        { value: 'none', label: 'No minimum' },
                        { value: '3', label: '3+ days' },
                        { value: '5', label: '5+ days' },
                        { value: '7', label: '7+ days' },
                        { value: '14', label: '14+ days' },
                        { value: '30', label: '30+ days' },
                        { value: 'custom', label: 'Custom min days' },
                      ]}
                      value={
                        draftFilters.inactiveMode === 'custom'
                          ? 'custom'
                          : draftFilters.inactiveMode === 'none'
                            ? 'none'
                            : draftFilters.inactivePreset
                      }
                      onChange={(val) => {
                        if (!val || val === 'none') {
                          setDraftFilters((prev) => ({
                            ...prev,
                            inactiveMode: 'none',
                            inactivePreset: '3',
                            inactiveCustom: '',
                          }));
                        } else if (val === 'custom') {
                          setDraftFilters((prev) => ({
                            ...prev,
                            inactiveMode: 'custom',
                            inactivePreset: '3',
                            inactiveCustom: prev.inactiveCustom || '',
                          }));
                        } else {
                          setDraftFilters((prev) => ({
                            ...prev,
                            inactiveMode: 'preset',
                            inactivePreset: val,
                            inactiveCustom: '',
                          }));
                        }
                      }}
                    />
                    {draftFilters.inactiveMode === 'custom' && (
                      <TextInput
                        size="sm"
                        placeholder="e.g. 10 or 10k"
                        value={draftFilters.inactiveCustom}
                        onChange={(e) =>
                          setDraftFilters((prev) => ({ ...prev, inactiveCustom: e.currentTarget.value }))
                        }
                      />
                    )}
                  </Stack>
                </Paper>
              </Grid.Col>

              <Grid.Col span={{ base: 12, sm: 6, md: 4, lg: 4 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap={6}>
                    <Group gap="xs" justify="space-between">
                      <Text size="sm" fw={600}>Min Previous Beige Loot</Text>
                      {draftFilters.lootMode !== 'none' && (
                        <Anchor
                          size="xs"
                          onClick={() =>
                            setDraftFilters((prev) => ({
                              ...prev,
                              lootMode: 'none',
                              lootPreset: '0',
                              lootCustom: '',
                            }))
                          }
                        >
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">Presets or custom min (same parsing as table column).</Text>
                    <Select
                      size="sm"
                      data={[
                        { value: '0', label: 'No minimum' },
                        { value: '5000000', label: '$5 million' },
                        { value: '10000000', label: '$10 million' },
                        { value: '20000000', label: '$20 million' },
                        { value: 'custom', label: 'Custom minimum' },
                      ]}
                      value={
                        draftFilters.lootMode === 'custom'
                          ? 'custom'
                          : draftFilters.lootMode === 'none'
                            ? '0'
                            : draftFilters.lootPreset
                      }
                      onChange={(val) => {
                        if (!val || val === '0') {
                          setDraftFilters((prev) => ({
                            ...prev,
                            lootMode: 'none',
                            lootPreset: '0',
                            lootCustom: '',
                          }));
                        } else if (val === 'custom') {
                          setDraftFilters((prev) => ({
                            ...prev,
                            lootMode: 'custom',
                            lootPreset: '0',
                            lootCustom: prev.lootCustom || '',
                          }));
                        } else {
                          setDraftFilters((prev) => ({
                            ...prev,
                            lootMode: 'preset',
                            lootPreset: val,
                            lootCustom: '',
                          }));
                        }
                      }}
                    />
                    {draftFilters.lootMode === 'custom' && (
                      <TextInput
                        size="sm"
                        placeholder="e.g. 5m or 7500000"
                        value={draftFilters.lootCustom}
                        onChange={(e) =>
                          setDraftFilters((prev) => ({ ...prev, lootCustom: e.currentTarget.value }))
                        }
                      />
                    )}
                  </Stack>
                </Paper>
              </Grid.Col>

              <Grid.Col span={{ base: 12, md: 8, lg: 8 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap="xs">
                    <Group gap="xs" justify="space-between">
                      <Text size="sm" fw={600}>Score Range</Text>
                      {(() => {
                        const defaultMode = appliedNationId ? 'yours' : 'custom';
                        const defaultScore = data?.attacker?.score?.toString() || '';
                        const isDefault =
                          draftFilters.scoreMode === defaultMode &&
                          draftFilters.yourScore === defaultScore &&
                          !draftFilters.minScore &&
                          !draftFilters.maxScore;
                        return !isDefault;
                      })() && (
                        <Anchor size="xs" onClick={() => {
                          const nationScore = data?.attacker?.score?.toString() || '';
                          setDraftFilters(prev => ({
                            ...prev,
                            scoreMode: appliedNationId ? 'yours' : 'custom',
                            yourScore: nationScore,
                            minScore: '',
                            maxScore: '',
                          }));
                        }}>
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">Use your score or set custom limits.</Text>
                    <Select
                      size="sm"
                      data={[
                        { value: 'custom', label: 'Custom min/max' },
                        { value: 'yours', label: 'Based on your score (0.75x - 2.5x)', disabled: !appliedNationId },
                      ]}
                      value={draftFilters.scoreMode}
                      onChange={(val) => setDraftFilters(prev => ({ ...prev, scoreMode: val || 'custom' }))}
                    />
                    
                    {draftFilters.scoreMode === 'yours' ? (
                      <NumberInput
                        size="sm"
                        label="Your Score"
                        placeholder={appliedNationId ? "Auto-filled from nation" : "Set nation ID above"}
                        value={draftFilters.yourScore}
                        onChange={(val) => setDraftFilters(prev => ({ ...prev, yourScore: val?.toString() || '' }))}
                        min={0}
                        step={0.01}
                        disabled={!appliedNationId}
                      />
                    ) : (
                      <Grid gutter="sm">
                        <Grid.Col span={6}>
                          <NumberInput
                            size="sm"
                            label="Min Score"
                            placeholder="Min"
                            value={draftFilters.minScore}
                            onChange={(val) => setDraftFilters(prev => ({ ...prev, minScore: val?.toString() || '' }))}
                            min={0}
                            step={0.1}
                          />
                        </Grid.Col>
                        <Grid.Col span={6}>
                          <NumberInput
                            size="sm"
                            label="Max Score"
                            placeholder="Max"
                            value={draftFilters.maxScore}
                            onChange={(val) => setDraftFilters(prev => ({ ...prev, maxScore: val?.toString() || '' }))}
                            min={0}
                            step={0.1}
                          />
                        </Grid.Col>
                      </Grid>
                    )}
                  </Stack>
                </Paper>
              </Grid.Col>

              <Grid.Col span={{ base: 12, sm: 6, md: 4, lg: 4 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap={6}>
                    <Text size="sm" fw={600}>Performance Filter</Text>
                    <Text size="xs" c="dimmed">
                      Filters out "bad" targets: nations with negative income, stronger ground force than you, or $0 previous beige loot.
                    </Text>
                    <Switch
                      size="sm"
                      label="Hide low-value targets"
                      checked={draftFilters.performance}
                      onChange={(event) =>
                        setDraftFilters(prev => ({ ...prev, performance: event.currentTarget.checked }))
                      }
                    />
                  </Stack>
                </Paper>
              </Grid.Col>
            </Grid>

            <Group gap="sm" justify="center">
              <Button
                leftSection={<IconX size={16} />}
                onClick={resetFilters}
                variant="light"
                color="gray"
                size="sm"
                disabled={isLoading}
              >
                Reset All
              </Button>
            </Group>
          </Stack>
        </Paper>

        {/* Discord Link Disclaimer */}
        {!isLoading && !discordLinked && !discordAuthenticated && (
          <Alert
            icon={<IconBrandDiscord size={16} />}
            title="Beige Reminders"
            color="blue"
            variant="light"
          >
            <Stack gap="sm" align="flex-start">
              <Text size="sm">Log in with Discord to set beige reminders.</Text>
              <Button
                component="a"
                href={getDiscordLoginUrl('/raids')}
                size="md"
                color="indigo"
                variant="filled"
                leftSection={<IconBrandDiscord size={14} />}
                style={{ textDecoration: 'none' }}
                styles={{ root: { textDecoration: 'none' } }}
              >
                Login with Discord
              </Button>
            </Stack>
          </Alert>
        )}
        {!isLoading && discordAuthenticated && !discordLinked && (
          <Alert icon={<IconInfoCircle size={16} />} title="Reminder setup" color="blue" variant="light">
            <Stack gap="sm" align="flex-start">
              <Text size="sm">
                Link your Politics & War nation using the button below to enable beige reminders, or use{' '}
                <strong>/verify</strong> in the Discord bot.
              </Text>
              <Button size="xs" variant="light" color="blue" onClick={() => setVerifyModalOpen(true)}>
                Link Nation
              </Button>
            </Stack>
          </Alert>
        )}
        <VerifyNationModal
          opened={verifyModalOpen}
          onClose={() => setVerifyModalOpen(false)}
          onVerified={() => {
            void refetchLinkedNation();
            void refetch();
          }}
        />

        {/* Header */}
        <Stack gap="xs">
          <Title order={2}>Raid Targets</Title>
          <Text c="dimmed">
            Find profitable targets to raid. Click column headers to sort,
            use filters to narrow down results.
          </Text>
        </Stack>

        {/* Table */}
        <Box pos="relative">
          {isFetching && !isInitialLoading && (
            <Box
              pos="absolute"
              top={0}
              left={0}
              right={0}
              bottom={0}
              style={{
                zIndex: 3,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                backgroundColor: 'rgba(0, 0, 0, 0.35)',
                backdropFilter: 'blur(1px)',
                borderRadius: 'var(--mantine-radius-md)',
                pointerEvents: 'none',
              }}
            >
              <Loader size="lg" color="orange" />
              <Text size="sm" fw={500} mt="xs" c="white">Updating...</Text>
            </Box>
          )}
          {isInitialLoading ? (
            <Paper withBorder radius="md" p="md">
              <Stack gap="xs">
                <Skeleton height={28} radius="sm" />
                <Skeleton height={18} radius="sm" />
                {Array.from({ length: 10 }).map((_, idx) => (
                  <Skeleton key={`raid-table-skeleton-${idx}`} height={26} radius="sm" />
                ))}
              </Stack>
            </Paper>
          ) : (
            <RaidsTable
              data={filteredTargets}
              allianceSelectOptions={allianceFilterOptions}
              positionSelectOptions={positionFilterOptions}
              discordAuthenticated={discordAuthenticated}
              discordLinked={discordLinked}
              damageAttackerNationId={
                discordLinked
                  ? appliedNationId ??
                    (data?.attacker?.id != null ? String(data.attacker.id) : undefined)
                  : undefined
              }
              onOpenVerifyNationModal={() => setVerifyModalOpen(true)}
              initialSorting={initialSorting}
              columnVisibility={columnVisibility}
              columnOrder={columnOrder}
              density="xs"
              columnFilters={columnFilters}
              onColumnVisibilityChange={setColumnVisibility}
              onColumnOrderChange={setColumnOrder}
              onDensityChange={() => {}}
              onColumnFiltersChange={handleColumnFiltersChange}
            />
          )}
        </Box>
      </Stack>
    </Container>
  );
}
