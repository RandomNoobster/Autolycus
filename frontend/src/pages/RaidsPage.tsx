/**
 * Raids Page
 *
 * Displays raid targets with token authentication.
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
} from '@mantine/core';
import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { IconX, IconAlertCircle, IconBrandDiscord, IconDownload } from '@tabler/icons-react';
import type {
  MRT_ColumnFiltersState,
  MRT_ColumnOrderState,
  MRT_DensityState,
  MRT_VisibilityState,
} from 'mantine-react-table';

import { fetchRaids, exchangeToken } from '@/api';
import { persistAccessTokenFromExchange } from '@/lib/accessTokenStorage';
import {
  useUrlParams,
  useNationId,
  useTablePersistence,
  usePersistedAccessToken,
  useRaidsSearchParams,
} from '@/hooks';
import { RaidsTable } from '@/components/raids';
import { TokenError, ErrorState, NationIdField } from '@/components/common';
import type { ApiError } from '@/types';

type TableSettings = {
  columnVisibility: MRT_VisibilityState;
  columnOrder: MRT_ColumnOrderState;
  density: MRT_DensityState;
  columnFilters: MRT_ColumnFiltersState;
};

const DEFAULT_TABLE_SETTINGS: TableSettings = {
  columnVisibility: {
    id: false,
    nationName: true,
    leaderName: false,
    allianceName: true,
    alliancePosition: true,
    numCities: true,
    color: true,
    nationLoot: true,
    daysInactive: true,
    monetaryNetIncome: false,
    netCashIncome: false,
    taxable: false,
    treasures: false,
    defSlots: true,
    timeSinceWar: true,
    soldiers: false,
    tanks: false,
    aircraft: false,
    ships: false,
    missiles: false,
    nukes: false,
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
    'nationLoot',
    'daysInactive',
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

const MAPPED_COLUMN_IDS = new Set([
  'allianceName',
  'beigeTurns',
  'defSlots',
  'daysInactive',
  'alliancePosition',
  'nationLoot',
]);


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

function migrateStoredAlliance(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((s) => String(s).trim()).filter(Boolean);
  }
  if (typeof value === 'string' && value.trim()) return [value.trim()];
  return [];
}


export function RaidsPage() {
  const { token: urlToken, initialColumnFilters, initialSorting } = useUrlParams();
  const { resolveToken } = usePersistedAccessToken('raids', urlToken);
  const { nationId: savedNationId, parseNationId, setNationId } = useNationId();
  const [searchParams, setSearchParams] = useRaidsSearchParams();

  // Handle Discord auth code → token exchange
  const code = searchParams.get('code');
  const [exchangedToken, setExchangedToken] = useState<string | null>(null);
  const [exchangeError, setExchangeError] = useState<string | null>(null);
  const awaitingFreshDiscordCode =
    Boolean(code) && !urlToken && !exchangedToken && !exchangeError;
  const token = awaitingFreshDiscordCode ? null : resolveToken(exchangedToken);
  const isExchangingCode = !!code && !token && !exchangeError;
  const exchangeInFlightRef = useRef(false);

  useEffect(() => {
    if (!code || urlToken || exchangeInFlightRef.current) return;
    exchangeInFlightRef.current = true;
    const doExchange = async () => {
      try {
        const response = await exchangeToken({ code });
        await persistAccessTokenFromExchange(response);
        setExchangedToken(response.token);
        setSearchParams((prev) => {
          const next = new URLSearchParams(prev);
          next.delete('code');
          next.delete('auto');
          next.delete('redirect');
          next.set('token', response.token);
          return next;
        }, { replace: true });
      } catch (err: any) {
        setExchangeError(err.message || 'Failed to authenticate with Discord.');
        exchangeInFlightRef.current = false;
      }
    };
    doExchange();
  }, [code, urlToken, setSearchParams]);

  const targetNationIds = searchParams.get('targetNationIds') || undefined;
  const attackerNationIdParam = searchParams.get('attackerNationId') || undefined;
  const useSavedTargets = searchParams.get('useSavedTargets') === 'true';
  const resolvedNationId = attackerNationIdParam || savedNationId;
  const [appliedNationId, setAppliedNationId] = useState(resolvedNationId);
  const [draftNationId, setDraftNationId] = useState(resolvedNationId);

  useEffect(() => {
    const nextNationId = attackerNationIdParam || savedNationId;
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
  }, [attackerNationIdParam, savedNationId, appliedNationId, parseNationId, setNationId]);

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

  // Active filters from URL (used for API call)
  const activeFilters = {
    alliance: parseAlliancesFromSearchParams(searchParams),
    beige: parseBoolean('beige'),
    maxWars: parseNumber('maxWars'),
    inactiveMinDays: parseNumber('inactiveMinDays'),
    scope: (searchParams.get('scope') as 'all' | 'apps_or_none' | 'no_alliance' | null) || undefined,
    minBeigeLoot: parseNumber('minBeigeLoot'),
    performance: parseBoolean('performance'),
    scoreMode: searchParams.get('scoreMode') || 'custom',
    yourScore: parseNumber('yourScore'),
    minScore: parseNumber('minScore'),
    maxScore: parseNumber('maxScore'),
  };

  // Local draft state for filters (before submit)
  const [draftFilters, setDraftFilters] = useState({
    alliance: parseAlliancesFromSearchParams(searchParams),
    beige: activeFilters.beige === true ? 'only' : activeFilters.beige === false ? 'hide' : 'all',
    maxWars: activeFilters.maxWars?.toString() || 'all',
    inactiveMinDays: activeFilters.inactiveMinDays?.toString() || 'none',
    scope: activeFilters.scope || 'all',
    minBeigeLoot: activeFilters.minBeigeLoot?.toString() || '0',
    performance: activeFilters.performance ?? false,
    scoreMode: activeFilters.scoreMode || (savedNationId ? 'yours' : 'custom'),
    yourScore: activeFilters.yourScore?.toString() || '',
    minScore: activeFilters.minScore?.toString() || '',
    maxScore: activeFilters.maxScore?.toString() || '',
  });

  const {
    columnVisibility,
    setColumnVisibility,
    columnOrder,
    setColumnOrder,
    density,
    setDensity,
  } = useTablePersistence('raids', RAIDS_TABLE_PERSISTENCE_DEFAULTS);

  const [columnFilters, setColumnFilters] = useState<MRT_ColumnFiltersState>(
    () => [...DEFAULT_TABLE_SETTINGS.columnFilters]
  );
  const prevColumnFiltersRef = useRef<MRT_ColumnFiltersState>(
    DEFAULT_TABLE_SETTINGS.columnFilters
  );
  const syncingFromFiltersRef = useRef(false);
  const urlFiltersAppliedRef = useRef(false);
  const filtersRestoredRef = useRef(false);
  const FILTER_STORAGE_KEY = 'autolycus-raids-filters-v1';
  const FILTER_QUERY_KEYS = [
    'alliance',
    'beige',
    'maxWars',
    'inactiveMinDays',
    'scope',
    'minBeigeLoot',
    'performance',
    'scoreMode',
    'yourScore',
    'minScore',
    'maxScore',
  ];

  // Fetch raids data - must be before any conditional returns
  const {
    data,
    isLoading,
    isFetching,
    error,
    refetch,
  } = useQuery({
    queryKey: ['raids', token, appliedNationId, targetNationIds, useSavedTargets],
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
      return fetchRaids(token ?? undefined, filters);
    },
    retry: false,
    enabled: !isExchangingCode,
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

  useEffect(() => {
    if (filtersRestoredRef.current) return;
    const hasUrlFilters = FILTER_QUERY_KEYS.some((key) => {
      if (key === 'alliance') return searchParams.getAll('alliance').some(Boolean);
      return searchParams.get(key) !== null;
    });
    if (hasUrlFilters) {
      filtersRestoredRef.current = true;
      return;
    }

    try {
      const raw = localStorage.getItem(FILTER_STORAGE_KEY);
      if (!raw) {
        filtersRestoredRef.current = true;
        return;
      }
      const stored = JSON.parse(raw) as Partial<typeof draftFilters>;
      if (stored.alliance !== undefined) {
        (stored as { alliance: string[] }).alliance = migrateStoredAlliance(stored.alliance);
      }
      setDraftFilters((prev) => ({ ...prev, ...stored }));

      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        FILTER_QUERY_KEYS.forEach((key) => next.delete(key));
        const alliances = stored.alliance !== undefined ? migrateStoredAlliance(stored.alliance) : [];
        for (const a of alliances) {
          if (a.trim()) next.append('alliance', a.trim());
        }
        if (stored.beige === 'only') next.set('beige', 'true');
        else if (stored.beige === 'hide') next.set('beige', 'false');
        if (stored.maxWars && stored.maxWars !== 'all') next.set('maxWars', stored.maxWars);
        if (stored.inactiveMinDays && stored.inactiveMinDays !== 'none') next.set('inactiveMinDays', stored.inactiveMinDays);
        if (stored.scope && stored.scope !== 'all') next.set('scope', stored.scope);
        if (stored.minBeigeLoot && stored.minBeigeLoot !== '0') next.set('minBeigeLoot', stored.minBeigeLoot);
        if (stored.performance) next.set('performance', 'true');
        if (stored.scoreMode) next.set('scoreMode', stored.scoreMode);
        if (stored.yourScore) next.set('yourScore', stored.yourScore);
        if (stored.minScore) next.set('minScore', stored.minScore);
        if (stored.maxScore) next.set('maxScore', stored.maxScore);
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
    if (urlFiltersAppliedRef.current || !initialColumnFilters.length) return;
    urlFiltersAppliedRef.current = true;
    syncingFromFiltersRef.current = true;
    setColumnFilters((prev) => mergeColumnFilters(prev, initialColumnFilters));
  }, [initialColumnFilters]);

  // Sync draft filters and URL params when column filters change from table interaction.
  // Side effects are in a useEffect (not inside a setState updater) to avoid
  // "Cannot update a component while rendering a different component" warnings.
  useEffect(() => {
    const previousFilters = prevColumnFiltersRef.current;
    prevColumnFiltersRef.current = columnFilters;

    if (syncingFromFiltersRef.current) {
      syncingFromFiltersRef.current = false;
      return;
    }

    const allianceCompareKey = (val: unknown) =>
      JSON.stringify([...allianceNamesFromColumnFilterValue(val)].sort());

    const changedIds: string[] = [];
    const getVal = (filters: MRT_ColumnFiltersState, id: string) =>
      filters.find((f) => f.id === id)?.value;

    MAPPED_COLUMN_IDS.forEach((id) => {
      const before = getVal(previousFilters, id);
      const after = getVal(columnFilters, id);
      if (id === 'allianceName') {
        if (allianceCompareKey(before) === allianceCompareKey(after)) return;
      } else if (JSON.stringify(before) === JSON.stringify(after)) {
        return;
      }
      changedIds.push(id);
    });

    if (changedIds.length) {
      if (changedIds.includes('allianceName')) {
        const names = allianceNamesFromColumnFilterValue(
          columnFilters.find((f) => f.id === 'allianceName')?.value
        );
        setDraftFilters((prev) => ({ ...prev, alliance: names }));
      }

      const resetDraft: Record<string, string | boolean> = {};
      const paramsToClear: string[] = [];

      changedIds.forEach((id) => {
        if (id === 'allianceName') {
          return;
        }
        if (id === 'beigeTurns') {
          resetDraft.beige = 'all';
          paramsToClear.push('beige');
        }
        if (id === 'defSlots') {
          resetDraft.maxWars = 'all';
          paramsToClear.push('maxWars');
        }
        if (id === 'daysInactive') {
          resetDraft.inactiveMinDays = 'none';
          paramsToClear.push('inactiveMinDays');
        }
        if (id === 'alliancePosition') {
          resetDraft.scope = 'all';
          paramsToClear.push('scope');
        }
        if (id === 'nationLoot') {
          resetDraft.minBeigeLoot = '0';
          paramsToClear.push('minBeigeLoot');
        }
      });

      if (Object.keys(resetDraft).length) {
        setDraftFilters((prevDraft) => ({ ...prevDraft, ...resetDraft }));
      }

      if (paramsToClear.length) {
        setSearchParams((prevParams) => {
          const nextParams = new URLSearchParams(prevParams);
          paramsToClear.forEach((key) => nextParams.delete(key));
          return nextParams;
        }, { replace: true });
      }
    }
  }, [columnFilters, setSearchParams]);

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

    // Max wars filter (using defSlots as defensive wars)
    if (activeFilters.maxWars !== undefined) {
      filtered = filtered.filter(nation => (3 - nation.defSlots) <= activeFilters.maxWars!);
    }

    // Inactivity filter
    if (activeFilters.inactiveMinDays !== undefined) {
      filtered = filtered.filter(nation => nation.daysInactive >= activeFilters.inactiveMinDays!);
    }

    // Scope filter
    if (activeFilters.scope === 'apps_or_none') {
      filtered = filtered.filter(nation => 
        nation.alliancePosition === 'NOALLIANCE' || nation.alliancePosition === 'APPLICANT'
      );
    } else if (activeFilters.scope === 'no_alliance') {
      filtered = filtered.filter(nation => nation.allianceId === '0');
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
      filtered = filtered.filter(nation => {
        const loot = parseFloat(nation.nationLoot.replace(/[^0-9.-]/g, ''));
        return nation.monetaryNetIncome > 0 && loot > 0;
      });
    }

    return filtered;
  }, [data?.targets, activeFilters]);

  const mappedColumnFiltersFromDraft = useCallback((): MRT_ColumnFiltersState => {
    const filters: MRT_ColumnFiltersState = [];
    if (draftFilters.alliance.length > 0) {
      filters.push({ id: 'allianceName', value: draftFilters.alliance });
    }
    if (data?.showBeige && (draftFilters.beige === 'only' || draftFilters.beige === 'hide')) {
      filters.push({ id: 'beigeTurns', value: draftFilters.beige });
    }
    if (draftFilters.maxWars !== 'all') {
      filters.push({ id: 'defSlots', value: draftFilters.maxWars });
    }
    if (draftFilters.inactiveMinDays !== 'none') {
      filters.push({ id: 'daysInactive', value: draftFilters.inactiveMinDays });
    }
    if (draftFilters.scope === 'apps_or_none') {
      filters.push({ id: 'alliancePosition', value: ['APPLICANT', 'NOALLIANCE'] });
    } else if (draftFilters.scope === 'no_alliance') {
      filters.push({ id: 'alliancePosition', value: ['NOALLIANCE'] });
    }
    if (draftFilters.minBeigeLoot !== '0') {
      filters.push({ id: 'nationLoot', value: draftFilters.minBeigeLoot });
    }
    return filters;
  }, [draftFilters, data?.showBeige]);

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
    setDraftFilters({
      alliance: [],
      beige: 'all',
      maxWars: 'all',
      inactiveMinDays: 'none',
      scope: 'all',
      minBeigeLoot: '0',
      performance: false,
      scoreMode: appliedNationId ? 'yours' : 'custom',
      yourScore: nationScore,
      minScore: '',
      maxScore: '',
    });
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      ['alliance', 'beige', 'maxWars', 'inactiveMinDays', 'scope', 'minBeigeLoot', 'performance', 'scoreMode', 'yourScore', 'minScore', 'maxScore'].forEach((k) =>
        next.delete(k)
      );
      return next;
    }, { replace: true });
    syncingFromFiltersRef.current = true;
    setColumnFilters((prev) => prev.filter((f) => !MAPPED_COLUMN_IDS.has(f.id)));
    try {
      localStorage.removeItem(FILTER_STORAGE_KEY);
    } catch (error) {
      console.warn('Failed to clear raids filter storage', error);
    }
  }, [setSearchParams, data?.attacker?.score, appliedNationId]);

  // Keep URL + localStorage in sync with draft UI (no debounce — debounced URL lag caused scoreMode query to fight the visible filters).
  useEffect(() => {
    if (!filtersRestoredRef.current) return;

    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      const preservedScore = {
        scoreMode: next.get('scoreMode'),
        yourScore: next.get('yourScore'),
        minScore: next.get('minScore'),
        maxScore: next.get('maxScore'),
      };

      // Clear old filter params
      FILTER_QUERY_KEYS.forEach(k => next.delete(k));

      // Apply new filters
      for (const a of draftFilters.alliance) {
        if (a.trim()) next.append('alliance', a.trim());
      }

      if (draftFilters.beige === 'only') next.set('beige', 'true');
      else if (draftFilters.beige === 'hide') next.set('beige', 'false');

      if (draftFilters.maxWars !== 'all') next.set('maxWars', draftFilters.maxWars);

      if (draftFilters.inactiveMinDays !== 'none') next.set('inactiveMinDays', draftFilters.inactiveMinDays);

      if (draftFilters.scope !== 'all') next.set('scope', draftFilters.scope);

      if (draftFilters.minBeigeLoot !== '0') next.set('minBeigeLoot', draftFilters.minBeigeLoot);

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

    try {
      localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(draftFilters));
    } catch (error) {
      console.warn('Failed to persist raids filters', error);
    }
  }, [draftFilters, setSearchParams]);

  type ColumnFiltersUpdater = MRT_ColumnFiltersState | ((prev: MRT_ColumnFiltersState) => MRT_ColumnFiltersState);

  const handleColumnFiltersChange = useCallback((updater: ColumnFiltersUpdater) => {
    setColumnFilters((prevFilters) =>
      typeof updater === 'function' ? updater(prevFilters) : updater
    );
  }, []);

  // Conditional returns AFTER all hooks

  if (error) {
    const apiError = error as unknown as ApiError;
    
    if (apiError.code === 'TOKEN_EXPIRED') {
      return <TokenError type="expired" message={apiError.message} dataType="raids" />;
    }
    if (apiError.code === 'TOKEN_INVALID') {
      return <TokenError type="invalid" message={apiError.message} dataType="raids" />;
    }
    
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
  const discordLinked = data?.discordLinked ?? false;
  const showBeige = data?.showBeige ?? false;

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
                      onChange={(val) => setDraftFilters(prev => ({ ...prev, beige: val || 'all' }))}
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
                      {draftFilters.scope !== 'all' && (
                        <Anchor size="xs" onClick={() => setDraftFilters(prev => ({ ...prev, scope: 'all' }))}>
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">Limit results by applicant or unaffiliated status.</Text>
                    <Select
                      size="sm"
                      data={[
                        { value: 'all', label: 'All nations' },
                        { value: 'apps_or_none', label: 'Applicants + No alliance' },
                        { value: 'no_alliance', label: 'No alliance only' },
                      ]}
                      value={draftFilters.scope}
                      onChange={(val) => setDraftFilters(prev => ({ ...prev, scope: (val || 'all') as 'all' | 'apps_or_none' | 'no_alliance' }))}
                    />
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
                          { value: '1', label: '≤1' },
                          { value: '2', label: '≤2' },
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
                      {draftFilters.inactiveMinDays !== 'none' && (
                        <Anchor size="xs" onClick={() => setDraftFilters(prev => ({ ...prev, inactiveMinDays: 'none' }))}>
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">Pick a minimum days inactive window.</Text>
                    <Group gap="xs" align="center" wrap="nowrap">
                      <Select
                        size="sm"
                        style={{ flex: 1 }}
                        data={[
                          { value: 'none', label: "Not" },
                          { value: '3', label: '3+ days' },
                          { value: '5', label: '5+ days' },
                          { value: '7', label: '7+ days' },
                          { value: '14', label: '14+ days' },
                          { value: '30', label: '30+ days' },
                        ]}
                        value={draftFilters.inactiveMinDays}
                        onChange={(val) => setDraftFilters(prev => ({ ...prev, inactiveMinDays: val || 'none' }))}
                      />
                      <Text size="sm" c="dimmed">
                        inactive
                      </Text>
                    </Group>
                  </Stack>
                </Paper>
              </Grid.Col>

              <Grid.Col span={{ base: 12, sm: 6, md: 4, lg: 4 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap={6}>
                    <Group gap="xs" justify="space-between">
                      <Text size="sm" fw={600}>Min Previous Beige Loot</Text>
                      {draftFilters.minBeigeLoot !== '0' && (
                        <Anchor size="xs" onClick={() => setDraftFilters(prev => ({ ...prev, minBeigeLoot: '0' }))}>
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">Require a minimum prior beige payout.</Text>
                    <Select
                      size="sm"
                      data={[
                        { value: '0', label: 'No minimum' },
                        { value: '5000000', label: '$5 million' },
                        { value: '10000000', label: '$10 million' },
                        { value: '20000000', label: '$20 million' },
                      ]}
                      value={draftFilters.minBeigeLoot}
                      onChange={(val) => setDraftFilters(prev => ({ ...prev, minBeigeLoot: val || '0' }))}
                    />
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
        {!isLoading && !discordLinked && (
          <Alert
            icon={<IconBrandDiscord size={16} />}
            title="Beige Reminders"
            color="blue"
            variant="light"
          >
            <Text size="sm">
              To set beige reminder notifications, access this page using a link from the Autolycus Discord bot.
              Run <Text span c="blue" fw={600} ff="monospace">/raids</Text> in any server where the bot is present to get a personalized link with reminder access.
            </Text>
          </Alert>
        )}
        {/* Auth code exchange error */}
        {exchangeError && (
          <Alert
            icon={<IconAlertCircle size={16} />}
            title="Authentication Error"
            color="orange"
            variant="light"
          >
            <Text size="sm">{exchangeError}</Text>
          </Alert>
        )}

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
              token={token}
              showBeige={showBeige}
              discordLinked={discordLinked}
              initialSorting={initialSorting}
              columnVisibility={columnVisibility}
              columnOrder={columnOrder}
              density={density}
              columnFilters={columnFilters}
              onColumnVisibilityChange={setColumnVisibility}
              onColumnOrderChange={setColumnOrder}
              onDensityChange={setDensity}
              onColumnFiltersChange={handleColumnFiltersChange}
            />
          )}
        </Box>
      </Stack>
    </Container>
  );
}
