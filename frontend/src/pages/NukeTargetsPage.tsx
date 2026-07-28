import {
  Alert,
  Anchor,
  Badge,
  Box,
  Button,
  Container,
  Grid,
  Group,
  Loader,
  MultiSelect,
  NumberInput,
  Paper,
  SegmentedControl,
  Select,
  Skeleton,
  Stack,
  Switch,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';
import { IconDownload, IconInfoCircle, IconX } from '@tabler/icons-react';
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type {
  MRT_ColumnOrderState,
  MRT_DensityState,
} from 'mantine-react-table';

import { fetchNukeTargets } from '@/api/nukeTargets';
import { fetchLiveNationScore } from '@/api/raids';
import { getLinkedNation } from '@/api/auth';
import { ErrorState, JumpToTableButton, NationIdField } from '@/components/common';
import { NukeTargetsTable } from '@/components/nukeTargets/NukeTargetsTable';
import { useNationId, useNukeTargetsSearchParams, useTablePersistence } from '@/hooks';
import {
  buildNukeTargetsDraftFromSearchParams,
  DEFAULT_NUKE_TARGETS_DRAFT,
  effectiveInactiveMinString,
  NUKE_TARGETS_FILTER_STORAGE_KEY,
  parseNukeTargetsFiltersStorage,
  serializeNukeTargetsFilters,
  type NukeTargetsDraftFilters,
} from '@/lib/nukeTargetsDraftState';
import { NUKE_TARGET_FILTER_DOCS, NUKE_TARGETS_PAGE_GUIDE } from '@/lib/nukeTargetsColumnDocs';
import { parseNumericValue } from '@/lib/raidFilterParsing';
import { warRangeQueryBounds } from '@/lib/warRange';
import type { ApiError, NukeTarget } from '@/types';

function parseNationId(raw: string): string | null {
  const trimmed = raw.trim();
  if (/^\d+$/.test(trimmed)) return trimmed;
  const match = trimmed.match(/id=(\d+)/i);
  return match ? match[1] : null;
}

function parseOptionalBoolParam(sp: URLSearchParams, key: string): boolean | null {
  const val = sp.get(key);
  if (val === null) return null;
  return val === 'true' || val === '1';
}

function sortNukeTargets(
  rows: NukeTarget[],
  sortMode: NukeTargetsDraftFilters['sortMode']
): NukeTarget[] {
  const sorted = [...rows];
  const net = (v: number | null | undefined) => v ?? -Infinity;
  switch (sortMode) {
    case 'simMissile':
      sorted.sort((a, b) => net(b.simMissileNet) - net(a.simMissileNet));
      break;
    case 'nukeNet':
      sorted.sort((a, b) => net(b.nukeNet) - net(a.nukeNet));
      break;
    case 'nukeDamage':
      sorted.sort((a, b) => net(b.nukeDamage) - net(a.nukeDamage));
      break;
    case 'simNuke':
    default:
      sorted.sort((a, b) => net(b.simNukeNet) - net(a.simNukeNet));
      break;
  }
  return sorted;
}

function nukeDraftsEqual(a: NukeTargetsDraftFilters, b: NukeTargetsDraftFilters): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

const NUKE_TARGETS_FILTER_URL_KEYS = [
  'alliance',
  'allianceExclude',
  'allianceMode',
  'beige',
  'maxWars',
  'inactiveMinDays',
  'minMaxInfra',
  'minAvgInfra',
  'hideVds',
  'hideIronDome',
  'minScore',
  'maxScore',
  'scoreMode',
  'yourScore',
  'sortMode',
] as const;

function writeNukeDraftToSearchParams(
  prev: URLSearchParams,
  draft: NukeTargetsDraftFilters
): URLSearchParams {
  const next = new URLSearchParams(prev);
  NUKE_TARGETS_FILTER_URL_KEYS.forEach((k) => next.delete(k));

  if (draft.allianceMode === 'exclude') {
    next.set('allianceMode', 'exclude');
    draft.allianceExclude.forEach((a) => {
      if (a.trim()) next.append('allianceExclude', a.trim());
    });
  } else {
    draft.alliance.forEach((a) => {
      if (a.trim()) next.append('alliance', a.trim());
    });
  }

  if (draft.beige === 'only') next.set('beige', 'true');
  else if (draft.beige === 'hide') next.set('beige', 'false');
  else if (draft.beige === 'all') next.set('beige', 'all');

  if (draft.maxWars === 'all') next.set('maxWars', 'all');
  else next.set('maxWars', draft.maxWars);

  const inactive = effectiveInactiveMinString(draft);
  if (inactive) next.set('inactiveMinDays', inactive);

  if (draft.minMaxInfra) next.set('minMaxInfra', draft.minMaxInfra);
  if (draft.minAvgInfra) next.set('minAvgInfra', draft.minAvgInfra);
  if (draft.hideVds) next.set('hideVds', 'true');
  if (draft.hideIronDome) next.set('hideIronDome', 'true');

  if (draft.sortMode && draft.sortMode !== 'simNuke') next.set('sortMode', draft.sortMode);

  if (draft.scoreMode === 'yours') {
    next.set('scoreMode', 'yours');
    if (draft.yourScore) next.set('yourScore', draft.yourScore);
  } else {
    if (draft.scoreMode) next.set('scoreMode', draft.scoreMode);
    if (draft.minScore) next.set('minScore', draft.minScore);
    if (draft.maxScore) next.set('maxScore', draft.maxScore);
  }

  return next;
}

const NUKE_TARGETS_TABLE_DEFAULTS = {
  columnVisibility: {
    id: true,
    nationName: true,
    leaderName: true,
    allianceName: true,
    alliancePosition: true,
    numCities: true,
    score: true,
    simNukeNet: true,
    simMissileNet: true,
    nukeDamage: true,
    nukeDamageWithoutVds: false,
    nukeNet: true,
    missileDamage: false,
    missileDamageWithoutIronDome: false,
    nukeInfraLost: false,
    maxInfra: true,
    avgInfra: true,
    vds: true,
    ironDome: true,
    falloutShelter: false,
    defenderWarPolicy: false,
    daysInactive: true,
    defSlots: true,
    beigeTurns: true,
    simNukeShots: false,
    simMissileShots: false,
  },
  columnOrder: [
    'id',
    'nationName',
    'leaderName',
    'allianceName',
    'alliancePosition',
    'numCities',
    'score',
    'simNukeNet',
    'simMissileNet',
    'nukeDamage',
    'nukeNet',
    'maxInfra',
    'avgInfra',
    'vds',
    'ironDome',
    'daysInactive',
    'defSlots',
    'beigeTurns',
    'nukeDamageWithoutVds',
    'missileDamage',
    'missileDamageWithoutIronDome',
    'nukeInfraLost',
    'falloutShelter',
    'defenderWarPolicy',
    'simNukeShots',
    'simMissileShots',
    'mrt-row-spacer',
  ] as MRT_ColumnOrderState,
  density: 'xs' as MRT_DensityState,
};

export function NukeTargetsPage() {
  const [searchParams, setSearchParams] = useNukeTargetsSearchParams();
  const { nationId: savedNationId, setNationId } = useNationId();
  const isNarrowNationCard = useMediaQuery('(max-width: 36em)');

  const { data: linkedNationData, isFetched: linkedNationFetched } = useQuery({
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
  const linkedNationId = linkedNationData?.linked
    ? linkedNationData.nation_id
      ? String(linkedNationData.nation_id)
      : undefined
    : undefined;

  const attackerNationIdParam = searchParams.get('attackerNationId') || undefined;
  const resolvedNationId = attackerNationIdParam || savedNationId || undefined;
  const [draftNationId, setDraftNationId] = useState(resolvedNationId || '');
  const [appliedNationId, setAppliedNationId] = useState(resolvedNationId || '');
  const draftNationIdRef = useRef(draftNationId);
  draftNationIdRef.current = draftNationId;

  useEffect(() => {
    if (attackerNationIdParam) {
      const parsed = parseNationId(attackerNationIdParam) || attackerNationIdParam;
      if (parsed !== appliedNationId) {
        setAppliedNationId(parsed);
        setDraftNationId(parsed);
      }
      return;
    }

    // Linked nation only prefills when applied + draft are empty — never overrides a saved id.
    if (!appliedNationId && !draftNationIdRef.current) {
      const fallback = linkedNationId || savedNationId;
      if (fallback) {
        setAppliedNationId(fallback);
        setDraftNationId(fallback);
        if (linkedNationId && !savedNationId) {
          setNationId(linkedNationId);
        }
      }
      return;
    }

    if (!appliedNationId && savedNationId) {
      setAppliedNationId(savedNationId);
      setDraftNationId(savedNationId);
    }
  }, [
    attackerNationIdParam,
    linkedNationId,
    linkedNationFetched,
    savedNationId,
    appliedNationId,
    setNationId,
  ]);

  const isTemporaryLinkedOverride = Boolean(
    linkedNationId && appliedNationId && String(appliedNationId) !== String(linkedNationId)
  );

  const urlAttrition = parseOptionalBoolParam(searchParams, 'attrition');
  const urlGuidingSatellite = parseOptionalBoolParam(searchParams, 'guidingSatellite');
  /**
   * null = omit override (API uses the nation's real warpolicy / GS).
   * Setting a boolean (URL or user toggle) is what triggers a targets refetch.
   */
  const [attritionOverride, setAttritionOverride] = useState<boolean | null>(urlAttrition);
  const [guidingSatelliteOverride, setGuidingSatelliteOverride] = useState<boolean | null>(
    urlGuidingSatellite
  );
  const tableSectionRef = useRef<HTMLDivElement>(null);

  const [draftFilters, setDraftFilters] = useState<NukeTargetsDraftFilters>(() =>
    buildNukeTargetsDraftFromSearchParams(searchParams, resolvedNationId, '')
  );

  const filtersRestoredRef = useRef(false);
  /** Gates the targets query until localStorage/URL filter hydrate finishes (avoids a throwaway fetch). */
  const [filtersReady, setFiltersReady] = useState(false);
  /**
   * After hydrating from localStorage, draft URL sync + persist effects must not run in the same
   * passive effect pass as the restore: they would still see the pre-restore draft and overwrite
   * the URL / localStorage with defaults.
   */
  const suppressDraftUrlSyncAndPersistRef = useRef(false);
  /** Nation id we already auto-filled yourScore for — prevents score thrashing when overriding. */
  const autofilledScoreNationRef = useRef<string | null>(null);
  const searchParamsKey = useMemo(() => searchParams.toString(), [searchParams]);

  useLayoutEffect(() => {
    suppressDraftUrlSyncAndPersistRef.current = false;
  });

  const {
    columnVisibility,
    setColumnVisibility,
    columnOrder,
    setColumnOrder,
    density,
    setDensity,
  } = useTablePersistence('nuke-targets', NUKE_TARGETS_TABLE_DEFAULTS);

  useEffect(() => {
    if (filtersRestoredRef.current) return;
    const nationKey = appliedNationId || savedNationId || undefined;
    const hasUrlFilters = NUKE_TARGETS_FILTER_URL_KEYS.some((key) => {
      if (key === 'alliance') return searchParams.getAll('alliance').some(Boolean);
      if (key === 'allianceExclude') return searchParams.getAll('allianceExclude').some(Boolean);
      return searchParams.get(key) !== null;
    });
    if (hasUrlFilters) {
      filtersRestoredRef.current = true;
      setFiltersReady(true);
      return;
    }

    const stored = parseNukeTargetsFiltersStorage(
      localStorage.getItem(NUKE_TARGETS_FILTER_STORAGE_KEY),
      nationKey
    );
    if (!stored) {
      filtersRestoredRef.current = true;
      setFiltersReady(true);
      return;
    }

    suppressDraftUrlSyncAndPersistRef.current = true;
    setDraftFilters(stored);
    setSearchParams((prev) => writeNukeDraftToSearchParams(prev, stored), { replace: true });
    filtersRestoredRef.current = true;
    setFiltersReady(true);
  }, [searchParams, setSearchParams, appliedNationId, savedNationId]);

  // Keep draft UI aligned with URL on back/forward (and other external query changes).
  useEffect(() => {
    if (!filtersRestoredRef.current) return;
    if (suppressDraftUrlSyncAndPersistRef.current) return;
    const fromUrl = buildNukeTargetsDraftFromSearchParams(
      searchParams,
      appliedNationId || savedNationId || undefined,
      ''
    );
    setDraftFilters((prev) => {
      // Don't let a stale URL yourScore (e.g. linked nation) overwrite draft after
      // we already autofilled for the applied/override nation.
      let next = fromUrl;
      if (
        autofilledScoreNationRef.current &&
        prev.scoreMode === 'yours' &&
        prev.yourScore
      ) {
        next = {
          ...fromUrl,
          scoreMode: prev.scoreMode,
          yourScore: prev.yourScore,
          minScore: prev.minScore,
          maxScore: prev.maxScore,
        };
      }
      return nukeDraftsEqual(prev, next) ? prev : next;
    });
    // Only re-hydrate when the query string changes — not when nation id alone updates.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- searchParamsKey tracks searchParams
  }, [searchParamsKey]);

  /** Active filters from URL (drives filteredTargets + API score bounds). */
  const appliedFilters = useMemo(
    () =>
      buildNukeTargetsDraftFromSearchParams(
        searchParams,
        appliedNationId || savedNationId || undefined,
        ''
      ),
    [searchParams, appliedNationId, savedNationId]
  );

  const appliedNationIdNum = appliedNationId ? parseInt(appliedNationId, 10) : NaN;
  const { data: liveAttacker, isError: liveScoreError, isFetched: liveScoreFetched } = useQuery({
    queryKey: ['live-nation-score', appliedNationId],
    queryFn: () => fetchLiveNationScore(appliedNationIdNum),
    enabled: Number.isFinite(appliedNationIdNum) && appliedNationIdNum > 0,
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
    retry: (failureCount, err) => {
      const code = (err as { code?: string } | null)?.code;
      if (code === 'RATE_LIMITED') return false;
      return failureCount < 1;
    },
  });

  const liveScoreForBounds =
    liveAttacker != null &&
    appliedNationId != null &&
    String(liveAttacker.id) === String(appliedNationId) &&
    Number.isFinite(liveAttacker.score)
      ? liveAttacker.score
      : null;

  // Prefer draftFilters (updated synchronously on localStorage hydrate) over URL-derived
  // appliedFilters so we don't fire a throwaway targets request before the router catches up.
  const apiScoreBounds = useMemo(() => {
    if (draftFilters.scoreMode === 'yours' && appliedNationId) {
      const score = parseNumericValue(draftFilters.yourScore);
      if (score > 0) {
        return warRangeQueryBounds(score);
      }
      if (liveScoreForBounds != null && liveScoreForBounds > 0) {
        return warRangeQueryBounds(liveScoreForBounds);
      }
    }
    const min = parseNumericValue(draftFilters.minScore);
    const max = parseNumericValue(draftFilters.maxScore);
    return {
      minScore: min > 0 ? min : 15,
      maxScore: max > 0 ? max : undefined,
    };
  }, [draftFilters, appliedNationId, liveScoreForBounds]);

  // Wait for this nation's score before fetching. A nation switch must not reuse the
  // previous war-range (score-filtered API slices omit the attacker → false "not found").
  // Exception: first visit (ref unset) with a hydrated yourScore from URL/localStorage.
  // If live score fails, stop blocking so a default-bounds fetch can still resolve the attacker.
  const yoursScoreUnconfirmed =
    draftFilters.scoreMode === 'yours' &&
    autofilledScoreNationRef.current !== appliedNationId;
  const hasBootstrapYourScore =
    autofilledScoreNationRef.current == null &&
    parseNumericValue(draftFilters.yourScore) > 0;
  const liveScoreFailed =
    liveScoreFetched && (liveScoreError || liveAttacker == null);
  const waitingForScoreBounds =
    !!appliedNationId &&
    filtersReady &&
    yoursScoreUnconfirmed &&
    !hasBootstrapYourScore &&
    !liveScoreFailed;

  const targetsQueryEnabled = !!appliedNationId && filtersReady && !waitingForScoreBounds;

  const { data, error, isLoading, isFetching, refetch } = useQuery({
    queryKey: [
      'nuke-targets',
      appliedNationId,
      apiScoreBounds.minScore,
      apiScoreBounds.maxScore,
      attritionOverride,
      guidingSatelliteOverride,
    ],
    queryFn: () =>
      fetchNukeTargets({
        attackerNationId: appliedNationId ? Number(appliedNationId) : undefined,
        minScore: apiScoreBounds.minScore,
        maxScore: apiScoreBounds.maxScore,
        vmode: false,
        ...(attritionOverride !== null ? { attrition: attritionOverride } : {}),
        ...(guidingSatelliteOverride !== null
          ? { guidingSatellite: guidingSatelliteOverride }
          : {}),
      }),
    enabled: targetsQueryEnabled,
    retry: false,
  });

  const nationLoadPending =
    !!appliedNationId &&
    (!filtersReady || waitingForScoreBounds || (targetsQueryEnabled && isLoading));

  /** Prefer live PnW score; only use API attacker when it matches the applied nation. */
  const cachedAttackerMatches =
    data?.attacker != null &&
    appliedNationId != null &&
    String(data.attacker.id) === String(appliedNationId);
  const effectiveAttackerScore =
    liveAttacker?.score ?? (cachedAttackerMatches ? data?.attacker?.score ?? null : null);
  const effectiveAttackerName =
    liveAttacker?.nationName ??
    (cachedAttackerMatches ? data?.attacker?.nation_name ?? null : null);
  const effectiveAttackerScoreText =
    effectiveAttackerScore != null ? String(effectiveAttackerScore) : '';

  const isInitialLoading = nationLoadPending;

  /** Stay true across attrition/GS refetches; only reset when the applied nation changes. */
  const [damageModsReadyFor, setDamageModsReadyFor] = useState<string | null>(null);
  useEffect(() => {
    setDamageModsReadyFor(null);
  }, [appliedNationId]);
  useEffect(() => {
    if (
      appliedNationId &&
      data?.attacker &&
      String(data.attacker.id) === String(appliedNationId)
    ) {
      setDamageModsReadyFor(appliedNationId);
    }
  }, [appliedNationId, data?.attacker]);
  const hasDamageModOverrides =
    attritionOverride !== null || guidingSatelliteOverride !== null;
  const damageModsPending =
    !!appliedNationId &&
    !hasDamageModOverrides &&
    damageModsReadyFor !== appliedNationId;

  const attritionEnabled =
    attritionOverride ?? data?.attacker?.warpolicy === 'Attrition';
  const guidingSatelliteEnabled =
    guidingSatelliteOverride ?? Boolean(data?.attacker?.guidingSatellite);

  useEffect(() => {
    if (!appliedNationId) return;
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (attritionOverride === null) next.delete('attrition');
        else next.set('attrition', attritionOverride ? 'true' : 'false');
        if (guidingSatelliteOverride === null) next.delete('guidingSatellite');
        else next.set('guidingSatellite', guidingSatelliteOverride ? 'true' : 'false');
        if (next.toString() === prev.toString()) return prev;
        return next;
      },
      { replace: true }
    );
  }, [appliedNationId, attritionOverride, guidingSatelliteOverride, setSearchParams]);

  const prevAppliedNationIdRef = useRef(appliedNationId);
  useEffect(() => {
    const prev = prevAppliedNationIdRef.current;
    if (prev === appliedNationId) return;
    prevAppliedNationIdRef.current = appliedNationId;
    // New nation → drop overrides so the first fetch uses DB warpolicy / GS.
    setAttritionOverride(null);
    setGuidingSatelliteOverride(null);
    // Only clear score when switching between two concrete nations (not initial hydrate).
    if (!prev || !appliedNationId) return;
    autofilledScoreNationRef.current = null;
    setDraftFilters((prevDraft) =>
      prevDraft.scoreMode === 'yours' && prevDraft.yourScore
        ? { ...prevDraft, yourScore: '' }
        : prevDraft
    );
  }, [appliedNationId]);

  useEffect(() => {
    if (!appliedNationId) {
      autofilledScoreNationRef.current = null;
      setDraftFilters((prev) => (prev.scoreMode !== 'yours' ? prev : { ...prev, scoreMode: 'custom' }));
      return;
    }

    if (autofilledScoreNationRef.current === appliedNationId) return;

    const liveMatches =
      liveAttacker != null && String(liveAttacker.id) === String(appliedNationId);
    const liveFailed = liveScoreFetched && (liveScoreError || liveAttacker == null);

    let score: number | null = null;
    if (liveMatches) {
      score = liveAttacker.score;
    } else if (liveFailed && cachedAttackerMatches) {
      score = data?.attacker?.score ?? null;
    } else {
      return;
    }
    if (score == null || !Number.isFinite(Number(score))) return;

    const s = String(score);
    autofilledScoreNationRef.current = appliedNationId;
    setDraftFilters((prev) => {
      const sameScore =
        prev.yourScore === s ||
        (prev.yourScore !== '' &&
          Number.isFinite(Number(prev.yourScore)) &&
          Math.abs(Number(prev.yourScore) - Number(score)) < 0.005);
      if (prev.scoreMode === 'custom' && (prev.minScore || prev.maxScore)) {
        if (sameScore) return prev;
        return { ...prev, yourScore: s };
      }
      if (prev.scoreMode === 'yours' && sameScore) return prev;
      return { ...prev, yourScore: s, scoreMode: 'yours' };
    });
  }, [
    appliedNationId,
    liveAttacker,
    liveScoreError,
    liveScoreFetched,
    cachedAttackerMatches,
    data?.attacker?.score,
  ]);

  const allianceOptions = useMemo(() => {
    const names = new Set<string>();
    (data?.targets ?? []).forEach((t) => {
      if (t.allianceName && t.allianceName !== 'None') names.add(t.allianceName);
    });
    draftFilters.alliance.forEach((n) => names.add(n));
    draftFilters.allianceExclude.forEach((n) => names.add(n));
    return [...names].sort().map((n) => ({ value: n, label: n }));
  }, [data?.targets, draftFilters.alliance, draftFilters.allianceExclude]);

  const filteredTargets = useMemo(() => {
    let rows = [...(data?.targets ?? [])];

    if (appliedFilters.beige === 'only') {
      rows = rows.filter((r) => r.beigeTurns > 0);
    } else if (appliedFilters.beige === 'hide') {
      rows = rows.filter((r) => r.beigeTurns <= 0);
    }

    if (appliedFilters.maxWars !== 'all') {
      const maxWars = Number(appliedFilters.maxWars);
      rows = rows.filter((r) => r.defSlots <= maxWars);
    }

    const inactiveMin = effectiveInactiveMinString(appliedFilters);
    if (inactiveMin) {
      const minDays = parseNumericValue(inactiveMin);
      rows = rows.filter((r) => r.daysInactive >= minDays);
    }

    if (appliedFilters.allianceMode === 'exclude' && appliedFilters.allianceExclude.length) {
      const exclude = new Set(appliedFilters.allianceExclude.map((a) => a.toLowerCase()));
      rows = rows.filter((r) => !exclude.has(r.allianceName.toLowerCase()));
    } else if (appliedFilters.allianceMode === 'include' && appliedFilters.alliance.length) {
      const include = new Set(appliedFilters.alliance.map((a) => a.toLowerCase()));
      rows = rows.filter((r) => include.has(r.allianceName.toLowerCase()));
    }

    const minMaxInfra = parseNumericValue(appliedFilters.minMaxInfra);
    if (minMaxInfra > 0) {
      rows = rows.filter((r) => (r.maxInfra ?? 0) >= minMaxInfra);
    }

    const minAvgInfra = parseNumericValue(appliedFilters.minAvgInfra);
    if (minAvgInfra > 0) {
      rows = rows.filter((r) => (r.avgInfra ?? 0) >= minAvgInfra);
    }

    if (appliedFilters.hideVds) {
      rows = rows.filter((r) => !r.vds);
    }
    if (appliedFilters.hideIronDome) {
      rows = rows.filter((r) => !r.ironDome);
    }

    return sortNukeTargets(rows, appliedFilters.sortMode);
  }, [data?.targets, appliedFilters]);

  useEffect(() => {
    if (!filtersRestoredRef.current) return;
    if (suppressDraftUrlSyncAndPersistRef.current) return;

    setSearchParams(
      (prev) => {
        const next = writeNukeDraftToSearchParams(prev, draftFilters);
        if (next.toString() === prev.toString()) return prev;
        return next;
      },
      { replace: true }
    );
    try {
      localStorage.setItem(
        NUKE_TARGETS_FILTER_STORAGE_KEY,
        serializeNukeTargetsFilters(draftFilters)
      );
    } catch (error) {
      console.warn('Failed to persist nuke targets filters', error);
    }
  }, [draftFilters, setSearchParams]);

  const resetFilters = useCallback(() => {
    const nationScore = effectiveAttackerScoreText;
    const defaults = DEFAULT_NUKE_TARGETS_DRAFT({
      scoreMode: appliedNationId ? 'yours' : 'custom',
      yourScore: nationScore,
    });
    setDraftFilters(defaults);
    setSearchParams((prev) => writeNukeDraftToSearchParams(prev, defaults), { replace: true });
    try {
      localStorage.removeItem(NUKE_TARGETS_FILTER_STORAGE_KEY);
    } catch (error) {
      console.warn('Failed to clear nuke targets filter storage', error);
    }
  }, [appliedNationId, effectiveAttackerScoreText, setSearchParams]);

  const attackerPolicy = data?.attacker?.warpolicy || '';
  const targetsError = error as unknown as ApiError | null;

  return (
    <Container size="xl" py="md">
      <Stack gap="md">
        <Group justify="space-between" align="flex-start" wrap="wrap">
          <Stack gap={4}>
            <Title order={2}>Nuke Targets</Title>
            <Text c="dimmed">
              Find nations to burn in Attrition wars, ranked by potential damage from nukes and
              missiles.
            </Text>
          </Stack>
        </Group>

        <Paper withBorder radius="md" p="lg">
          <Stack gap="sm">
            <Group justify="space-between" wrap="wrap" align="flex-start">
              <Group gap="xs">
                <Title order={3}>Your Nation</Title>
                <Badge color="blue" variant="light">
                  Optional
                </Badge>
              </Group>
              {(effectiveAttackerName || effectiveAttackerScore != null) &&
                appliedNationId &&
                (!nationLoadPending || liveAttacker) && (
                <Group
                  gap="xs"
                  wrap="wrap"
                  align="center"
                  justify={isNarrowNationCard ? 'flex-start' : 'flex-end'}
                  w={isNarrowNationCard ? '100%' : 'auto'}
                  style={{ flex: '1 1 auto', minWidth: 0, maxWidth: '100%' }}
                >
                  <Text size="sm" c="dimmed" style={{ wordBreak: 'break-word', maxWidth: '100%' }}>
                    {effectiveAttackerName}
                  </Text>
                  <Badge variant="light" color="blue" style={{ flexShrink: 0 }}>
                    Score:{' '}
                    {effectiveAttackerScore != null
                      ? effectiveAttackerScore.toFixed(2)
                      : 'N/A'}
                  </Badge>
                  {attackerPolicy ? (
                    <Badge variant="outline" style={{ flexShrink: 0 }}>
                      Nation policy: {attackerPolicy}
                    </Badge>
                  ) : null}
                </Group>
              )}
            </Group>
            <Text size="sm" c="dimmed">
              Load your nation for personalized damage math and score-based target range.
            </Text>
            <NationIdField
              label="Nation ID"
              placeholder="Nation ID or link"
              size="sm"
              value={appliedNationId || draftNationId || ''}
              disableWhenUnchanged
              onSubmit={(raw) => {
                const parsed = parseNationId(raw);
                if (parsed) {
                  setAppliedNationId(parsed);
                  setDraftNationId(parsed);
                  // Page-only override — keep localStorage / linked home nation for restore.
                  setAttritionOverride(null);
                  setGuidingSatelliteOverride(null);
                  setSearchParams(
                    (prev) => {
                      const next = new URLSearchParams(prev);
                      next.set('attackerNationId', parsed);
                      next.delete('attrition');
                      next.delete('guidingSatellite');
                      return next;
                    },
                    { replace: true }
                  );
                }
              }}
              buttonLabel="Load Nation"
              buttonIcon={<IconDownload size={14} />}
              loading={nationLoadPending}
              inputProps={{ style: { maxWidth: 260 } }}
              warningMessage={data?.warning || null}
            />
            {isTemporaryLinkedOverride && (
              <Alert color="yellow" variant="light" title="Temporary Override" mt="sm">
                <Stack gap="sm">
                  <Text size="sm">
                    You are currently overriding your linked nation ({linkedNationId}) for this page.
                  </Text>
                  <Button
                    size="xs"
                    variant="light"
                    color="yellow"
                    w="fit-content"
                    onClick={() => {
                      if (!linkedNationId) return;
                      setAppliedNationId(linkedNationId);
                      setDraftNationId(linkedNationId);
                      setNationId(linkedNationId);
                      setAttritionOverride(null);
                      setGuidingSatelliteOverride(null);
                      setSearchParams(
                        (prev) => {
                          const next = new URLSearchParams(prev);
                          next.set('attackerNationId', linkedNationId);
                          next.delete('attrition');
                          next.delete('guidingSatellite');
                          return next;
                        },
                        { replace: true }
                      );
                    }}
                  >
                    Use linked nation
                  </Button>
                </Stack>
              </Alert>
            )}
            <Stack gap={6} mt="xs">
              <Text size="sm" fw={600}>
                Damage modifiers
              </Text>
              <Text size="xs" c="dimmed">
                {NUKE_TARGET_FILTER_DOCS.damageMods}
              </Text>
              <Switch
                label="Attrition war policy"
                description="+10% infrastructure damage dealt with missiles and nukes."
                checked={Boolean(attritionEnabled)}
                disabled={!appliedNationId || damageModsPending}
                onChange={(event) => {
                  setAttritionOverride(event.currentTarget.checked);
                }}
              />
              <Switch
                label="Guiding Satellite"
                description="+20% missile and nuke infrastructure damage."
                checked={Boolean(guidingSatelliteEnabled)}
                disabled={!appliedNationId || damageModsPending}
                onChange={(event) => {
                  setGuidingSatelliteOverride(event.currentTarget.checked);
                }}
              />
            </Stack>
            {!appliedNationId ? (
              <Alert color="yellow" icon={<IconInfoCircle size={16} />} variant="light">
                Load your nation to calculate damage metrics and simulated war net damage.
              </Alert>
            ) : null}
          </Stack>
        </Paper>

        <Paper withBorder radius="md" p="lg">
          <Stack gap="md">
            <Stack gap={4}>
              <Title order={3}>How this page works</Title>
              <Text size="sm" c="dimmed">
                A quick guide to the numbers below, written for Attrition wars in Politics &amp; War.
              </Text>
            </Stack>
            <Stack gap="sm">
              {NUKE_TARGETS_PAGE_GUIDE.map((section) => (
                <Stack key={section.title} gap={4}>
                  <Text size="sm" fw={600}>
                    {section.title}
                  </Text>
                  <Text size="sm" c="dimmed" lh={1.55}>
                    {section.body}
                  </Text>
                </Stack>
              ))}
            </Stack>
          </Stack>
        </Paper>

        <Paper withBorder radius="md" p="lg">
          <Stack gap="sm">
            <Stack gap={4}>
              <Title order={3}>Target Filters</Title>
              <Text size="sm" c="dimmed">
                Refine the target list. Hover column headers for definitions; use table filters for
                per-column minimums.
              </Text>
            </Stack>

            <Grid gutter={{ base: 'sm', sm: 'md' }}>
              <Grid.Col span={{ base: 12, md: 8, lg: 8 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap={6}>
                    <Group gap="xs" justify="space-between">
                      <Text size="sm" fw={600}>
                        Score Range
                      </Text>
                      {(() => {
                        const defaultMode = appliedNationId ? 'yours' : 'custom';
                        const defaultScore = effectiveAttackerScoreText;
                        const isDefault =
                          draftFilters.scoreMode === defaultMode &&
                          draftFilters.yourScore === defaultScore &&
                          !draftFilters.minScore &&
                          !draftFilters.maxScore;
                        return !isDefault;
                      })() && (
                        <Anchor
                          size="xs"
                          onClick={() => {
                            const nationScore = effectiveAttackerScoreText;
                            setDraftFilters((prev) => ({
                              ...prev,
                              scoreMode: appliedNationId ? 'yours' : 'custom',
                              yourScore: nationScore,
                              minScore: '',
                              maxScore: '',
                            }));
                          }}
                        >
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">
                      {NUKE_TARGET_FILTER_DOCS.score}
                    </Text>
                    <Select
                      size="sm"
                      data={[
                        { value: 'custom', label: 'Custom min/max' },
                        {
                          value: 'yours',
                          label: 'Based on your score (0.75× – 2.5×)',
                          disabled: !appliedNationId,
                        },
                      ]}
                      value={draftFilters.scoreMode}
                      onChange={(v) =>
                        setDraftFilters((p) => ({ ...p, scoreMode: v || 'custom' }))
                      }
                    />
                    {draftFilters.scoreMode === 'yours' ? (
                      <NumberInput
                        size="sm"
                        label="Your score"
                        placeholder={appliedNationId ? 'Auto-filled from nation' : 'Set nation above'}
                        value={draftFilters.yourScore}
                        onChange={(v) =>
                          setDraftFilters((p) => ({ ...p, yourScore: String(v ?? '') }))
                        }
                        min={0}
                        step={0.01}
                        disabled={!appliedNationId}
                      />
                    ) : (
                      <Grid gutter="sm">
                        <Grid.Col span={6}>
                          <NumberInput
                            size="sm"
                            label="Min score"
                            placeholder="Min"
                            value={draftFilters.minScore}
                            onChange={(v) =>
                              setDraftFilters((p) => ({ ...p, minScore: String(v ?? '') }))
                            }
                            min={0}
                            step={0.1}
                          />
                        </Grid.Col>
                        <Grid.Col span={6}>
                          <NumberInput
                            size="sm"
                            label="Max score"
                            placeholder="Max"
                            value={draftFilters.maxScore}
                            onChange={(v) =>
                              setDraftFilters((p) => ({ ...p, maxScore: String(v ?? '') }))
                            }
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
                    <Group gap="xs" justify="space-between">
                      <Text size="sm" fw={600}>
                        Alliance Name
                      </Text>
                      {(draftFilters.alliance.length > 0 ||
                        draftFilters.allianceExclude.length > 0 ||
                        draftFilters.allianceMode === 'exclude') && (
                        <Anchor
                          size="xs"
                          onClick={() =>
                            setDraftFilters((p) => ({
                              ...p,
                              allianceMode: 'include',
                              alliance: [],
                              allianceExclude: [],
                            }))
                          }
                        >
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <SegmentedControl
                      size="xs"
                      fullWidth
                      data={[
                        { label: 'Include', value: 'include' },
                        { label: 'Exclude', value: 'exclude' },
                      ]}
                      value={draftFilters.allianceMode}
                      onChange={(v) =>
                        setDraftFilters((p) => {
                          const nextMode = v === 'exclude' ? 'exclude' : 'include';
                          if (nextMode === p.allianceMode) return p;
                          if (nextMode === 'exclude') {
                            return {
                              ...p,
                              allianceMode: 'exclude',
                              allianceExclude: p.alliance,
                              alliance: [],
                            };
                          }
                          return {
                            ...p,
                            allianceMode: 'include',
                            alliance: p.allianceExclude,
                            allianceExclude: [],
                          };
                        })
                      }
                    />
                    <Text size="xs" c="dimmed">
                      {NUKE_TARGET_FILTER_DOCS.alliances}
                    </Text>
                    <MultiSelect
                      size="sm"
                      placeholder={
                        draftFilters.allianceMode === 'exclude'
                          ? 'Select alliances to exclude'
                          : 'Select alliances'
                      }
                      data={allianceOptions}
                      value={
                        draftFilters.allianceMode === 'exclude'
                          ? draftFilters.allianceExclude
                          : draftFilters.alliance
                      }
                      onChange={(vals) =>
                        setDraftFilters((p) =>
                          p.allianceMode === 'exclude'
                            ? { ...p, allianceExclude: vals }
                            : { ...p, alliance: vals }
                        )
                      }
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
                      <Text size="sm" fw={600}>
                        Infrastructure
                      </Text>
                      {(draftFilters.minMaxInfra || draftFilters.minAvgInfra) && (
                        <Anchor
                          size="xs"
                          onClick={() =>
                            setDraftFilters((p) => ({ ...p, minMaxInfra: '', minAvgInfra: '' }))
                          }
                        >
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">
                      {NUKE_TARGET_FILTER_DOCS.infra}
                    </Text>
                    <Grid gutter="sm">
                      <Grid.Col span={6}>
                        <NumberInput
                          size="sm"
                          label="Min best-city infra"
                          placeholder="No min"
                          value={draftFilters.minMaxInfra}
                          onChange={(v) =>
                            setDraftFilters((p) => ({ ...p, minMaxInfra: String(v ?? '') }))
                          }
                          min={0}
                        />
                      </Grid.Col>
                      <Grid.Col span={6}>
                        <NumberInput
                          size="sm"
                          label="Min avg city infra"
                          placeholder="No min"
                          value={draftFilters.minAvgInfra}
                          onChange={(v) =>
                            setDraftFilters((p) => ({ ...p, minAvgInfra: String(v ?? '') }))
                          }
                          min={0}
                        />
                      </Grid.Col>
                    </Grid>
                  </Stack>
                </Paper>
              </Grid.Col>

              <Grid.Col span={{ base: 12, sm: 6, md: 4, lg: 4 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap={6}>
                    <Group gap="xs" justify="space-between">
                      <Text size="sm" fw={600}>
                        Defense Projects
                      </Text>
                      {(draftFilters.hideVds || draftFilters.hideIronDome) && (
                        <Anchor
                          size="xs"
                          onClick={() =>
                            setDraftFilters((p) => ({ ...p, hideVds: false, hideIronDome: false }))
                          }
                        >
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">
                      {NUKE_TARGET_FILTER_DOCS.defense}
                    </Text>
                    <Switch
                      size="sm"
                      label="Hide VDS targets"
                      checked={draftFilters.hideVds}
                      onChange={(e) =>
                        setDraftFilters((p) => ({ ...p, hideVds: e.currentTarget.checked }))
                      }
                    />
                    <Switch
                      size="sm"
                      label="Hide Iron Dome targets"
                      checked={draftFilters.hideIronDome}
                      onChange={(e) =>
                        setDraftFilters((p) => ({ ...p, hideIronDome: e.currentTarget.checked }))
                      }
                    />
                  </Stack>
                </Paper>
              </Grid.Col>

              <Grid.Col span={{ base: 12, sm: 6, md: 4, lg: 4 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap={6}>
                    <Group gap="xs" justify="space-between">
                      <Text size="sm" fw={600}>
                        Beige Status
                      </Text>
                      {draftFilters.beige !== 'hide' && (
                        <Anchor
                          size="xs"
                          onClick={() => setDraftFilters((p) => ({ ...p, beige: 'hide' }))}
                        >
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">
                      {NUKE_TARGET_FILTER_DOCS.beige}
                    </Text>
                    <Select
                      size="sm"
                      data={[
                        { value: 'all', label: 'Show all nations' },
                        { value: 'only', label: 'Only beige nations' },
                        { value: 'hide', label: 'Hide beige nations' },
                      ]}
                      value={draftFilters.beige}
                      onChange={(v) =>
                        setDraftFilters((p) => ({
                          ...p,
                          beige: (v as NukeTargetsDraftFilters['beige']) || 'all',
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
                      <Text size="sm" fw={600}>
                        Defensive Wars
                      </Text>
                      {draftFilters.maxWars !== '2' && (
                        <Anchor
                          size="xs"
                          onClick={() => setDraftFilters((p) => ({ ...p, maxWars: '2' }))}
                        >
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">
                      {NUKE_TARGET_FILTER_DOCS.defWars}
                    </Text>
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
                        onChange={(v) => setDraftFilters((p) => ({ ...p, maxWars: v || 'all' }))}
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
                      <Text size="sm" fw={600}>
                        Inactivity
                      </Text>
                      {draftFilters.inactiveMode !== 'none' && (
                        <Anchor
                          size="xs"
                          onClick={() =>
                            setDraftFilters((p) => ({
                              ...p,
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
                    <Text size="xs" c="dimmed">
                      {NUKE_TARGET_FILTER_DOCS.inactivity}
                    </Text>
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
                          setDraftFilters((p) => ({
                            ...p,
                            inactiveMode: 'none',
                            inactivePreset: '3',
                            inactiveCustom: '',
                          }));
                        } else if (val === 'custom') {
                          setDraftFilters((p) => ({
                            ...p,
                            inactiveMode: 'custom',
                            inactivePreset: '3',
                            inactiveCustom: p.inactiveCustom || '',
                          }));
                        } else {
                          setDraftFilters((p) => ({
                            ...p,
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
                          setDraftFilters((p) => ({ ...p, inactiveCustom: e.currentTarget.value }))
                        }
                      />
                    )}
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
                disabled={nationLoadPending}
              >
                Reset All
              </Button>
            </Group>
          </Stack>
        </Paper>

        <Stack
          gap="xs"
          ref={tableSectionRef}
          style={{ scrollMarginTop: 72 }}
        >
          <Group justify="space-between" align="flex-end" wrap="wrap">
            <Stack gap={4}>
              <Title order={2}>Target List</Title>
              <Text c="dimmed">
                Find vulnerable nations and calculate expected damage. Click a column header to sort by that column. Use filters to narrow down results.
              </Text>
            </Stack>
            {appliedNationId && data ? (
              <Text size="sm" c="dimmed">
                {filteredTargets.length.toLocaleString()} targets
              </Text>
            ) : null}
          </Group>
        </Stack>

        <JumpToTableButton targetRef={tableSectionRef} />

        {!appliedNationId ? (
          <Paper withBorder p="xl" radius="md">
            <Text ta="center" c="dimmed">
              Load your nation above to view the target table with damage calculations.
            </Text>
          </Paper>
        ) : targetsError ? (
          <ErrorState
            title="Failed to load nuke targets"
            message={targetsError.message || 'An unexpected error occurred'}
            onRetry={() => refetch()}
          />
        ) : (
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
                <Text size="sm" fw={500} mt="xs" c="white">
                  Updating...
                </Text>
              </Box>
            )}
            {isInitialLoading ? (
              <Paper withBorder radius="md" p="md">
                <Stack gap="xs">
                  <Skeleton height={28} radius="sm" />
                  <Skeleton height={18} radius="sm" />
                  {Array.from({ length: 10 }).map((_, idx) => (
                    <Skeleton key={`nuke-table-skeleton-${idx}`} height={26} radius="sm" />
                  ))}
                </Stack>
              </Paper>
            ) : data ? (
              <NukeTargetsTable
                data={filteredTargets}
                attackerNationId={appliedNationId}
                columnVisibility={columnVisibility}
                columnOrder={columnOrder}
                density={density}
                onColumnVisibilityChange={setColumnVisibility}
                onColumnOrderChange={setColumnOrder}
                onDensityChange={setDensity}
              />
            ) : null}
          </Box>
        )}
      </Stack>
    </Container>
  );
}
