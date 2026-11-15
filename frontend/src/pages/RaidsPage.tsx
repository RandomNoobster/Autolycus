/**
 * Raids Page
 *
 * Raid targets in the loaded nation's war range, filtered in the browser.
 *
 * Filter state has one owner, the sidebar draft. The URL mirrors it (for reloads and shared
 * links), the table's column filters hold the draft's mapped filters next to the table-only
 * ones, and localStorage keeps both. A change to a mapped column filter in the table is folded
 * back into the draft.
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
  Select,
  Switch,
  Button,
  MultiSelect,
  SegmentedControl,
  Alert,
  Loader,
  Skeleton,
} from '@mantine/core';
import {
  useState,
  useCallback,
  useMemo,
  useEffect,
  useRef,
  type SetStateAction,
} from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { IconX, IconBrandDiscord, IconDownload, IconInfoCircle, IconRefresh } from '@tabler/icons-react';
import type { MRT_ColumnFiltersState, MRT_SortingState } from 'mantine-react-table';

import { fetchLiveNationScore, fetchRaids, type RaidFilterParams } from '@/api';
import { getDiscordLoginUrl } from '@/api/auth';
import { isTransientApiError, toApiError } from '@/api/errors';
import {
  useNationId,
  useTablePersistence,
  useRaidsSearchParams,
  useSidebarDiscordSession,
} from '@/hooks';
import { RaidsTable } from '@/components/raids';
import {
  DebouncedNumberInput,
  PresetOrCustomFilterCard,
  ResetLink,
} from '@/components/raids/RaidsFilterControls';
import { ErrorState, JumpToTableButton, NationIdField, VerifyNationModal } from '@/components/common';
import { internalNavPath } from '@/lib/internalNavPath';
import { parseNumericValue } from '@/lib/raidFilterParsing';
import {
  DEFAULT_RAIDS_DRAFT_FILTERS,
  applyMappedColumnFilters,
  buildMappedColumnFiltersFromDraft,
  mappedFilterValuesEqual,
  validScore,
  writeRaidsDraftToSearchParams,
  type RaidsDraftFilters,
} from '@/lib/raidsDraftState';
import {
  RAIDS_FILTERS_LOCAL_STORAGE_KEY,
  RAIDS_MAPPED_FILTER_COLUMN_IDS,
  RAIDS_TABLE_DATA_COLUMN_IDS,
  loadInitialRaidsFilters,
  serializeRaidsFiltersStorageV3,
} from '@/lib/raidsFiltersStorage';
import { MIN_QUERY_SCORE, warRangeQueryBounds } from '@/lib/warRange';
import { useIsMobile } from '@/hooks/useIsMobile';
import { useLinkedNation } from '@/hooks/useLinkedNation';
import type { RaidTarget } from '@/types';
import { parseNationId } from '@/utils/nationId';

const RAIDS_TABLE_PERSISTENCE_DEFAULTS = {
  // Every column is visible by default.
  columnVisibility: {},
  columnOrder: [...RAIDS_TABLE_DATA_COLUMN_IDS, 'mrt-row-spacer'],
  density: 'xs' as const,
};

/** Hidden by default until 63f4157 (2026-04-03); older saved settings still froze them hidden. */
const RAIDS_TABLE_PERSISTENCE_OPTIONS = {
  legacyHiddenByDefault: [
    'id',
    'leaderName',
    'monetaryNetIncome',
    'netCashIncome',
    'taxable',
    'treasures',
    'soldiers',
    'tanks',
    'aircraft',
    'ships',
    'missiles',
    'nukes',
  ],
};

const MAPPED_COLUMN_IDS = RAIDS_MAPPED_FILTER_COLUMN_IDS;

const INACTIVE_OPTIONS = [
  { value: '3', label: '3+ days' },
  { value: '5', label: '5+ days' },
  { value: '7', label: '7+ days' },
  { value: '14', label: '14+ days' },
  { value: '30', label: '30+ days' },
];

const LOOT_OPTIONS = [
  { value: '5000000', label: '$5 million' },
  { value: '10000000', label: '$10 million' },
  { value: '20000000', label: '$20 million' },
];

/** A positive whole nation id as canonical digits ("0123" -> "123"), or undefined. */
function normalizeNationId(raw: string | null | undefined): string | undefined {
  if (!raw) return undefined;
  const parsed = parseNationId(raw);
  const n = parsed ? Number(parsed) : NaN;
  return Number.isSafeInteger(n) && n > 0 ? String(n) : undefined;
}

/** The sort from a shared link (`?sort=score&sortDir=desc`). */
function sortingFromSearchParams(sp: URLSearchParams): MRT_SortingState {
  const id = sp.get('sort');
  return id ? [{ id, desc: sp.get('sortDir') === 'desc' }] : [];
}

/** Same filters, ignoring order. */
function sameColumnFilters(a: MRT_ColumnFiltersState, b: MRT_ColumnFiltersState): boolean {
  if (a === b) return true;
  if (a.length !== b.length) return false;
  const byId = new Map(a.map((f) => [f.id, JSON.stringify(f.value)]));
  return b.every((f) => byId.get(f.id) === JSON.stringify(f.value));
}

function columnFilterValue(filters: MRT_ColumnFiltersState, id: string): unknown {
  return filters.find((f) => f.id === id)?.value;
}

/**
 * 'Hide bad targets': income and loot, plus a ground battle you can win when a nation is
 * loaded (without one there are no win chances to judge).
 */
function isGoodRaidTarget(nation: RaidTarget): boolean {
  return (
    (nation.groundWin == null || nation.groundWin >= 40) &&
    nation.monetaryNetIncome > 0 &&
    parseNumericValue(nation.nationLoot) > 0
  );
}

export function RaidsPage() {
  const [searchParams, setSearchParams] = useRaidsSearchParams();
  const { nationId: savedNationIdRaw, setNationId } = useNationId();
  const savedNationId = normalizeNationId(savedNationIdRaw);
  const session = useSidebarDiscordSession();
  const discordAuthenticated = session.status === 'signed_in';
  const { data: linkedNationData, refetch: refetchLinkedNation } = useLinkedNation();
  const linkedNationId = linkedNationData?.linked
    ? normalizeNationId(String(linkedNationData.nation_id ?? ''))
    : undefined;
  const attackerNationIdParam = normalizeNationId(searchParams.get('attackerNationId'));

  // The URL wins, then the saved nation; the linked nation fills an empty page when it arrives.
  const [appliedNationId, setAppliedNationId] = useState<string | undefined>(
    () => attackerNationIdParam ?? savedNationId
  );
  const appliedNationIdNum = appliedNationId ? Number(appliedNationId) : NaN;
  const [nationInputError, setNationInputError] = useState<string | null>(null);
  const [verifyModalOpen, setVerifyModalOpen] = useState(false);
  const isNarrowNationCard = useIsMobile();
  /** The user typed in the Nation ID field: a late linked-nation answer must not replace it. */
  const nationIdTypedRef = useRef(false);

  useEffect(() => {
    if (attackerNationIdParam) {
      setAppliedNationId(attackerNationIdParam);
      return;
    }
    if (!appliedNationId && linkedNationId && !nationIdTypedRef.current) {
      setAppliedNationId(linkedNationId);
      if (!savedNationId) setNationId(linkedNationId);
    }
  }, [attackerNationIdParam, linkedNationId, appliedNationId, savedNationId, setNationId]);

  // Read once at load: the URL, else storage. After that the draft owns the filters.
  const [initialFilters] = useState(() =>
    loadInitialRaidsFilters(searchParams, attackerNationIdParam ?? savedNationId)
  );
  const [initialSorting] = useState(() => sortingFromSearchParams(searchParams));
  const [draftFilters, setDraftFilters] = useState<RaidsDraftFilters>(initialFilters.draft);
  const [columnFilters, setColumnFilters] = useState<MRT_ColumnFiltersState>(
    initialFilters.columnFilters
  );
  const draftRef = useRef(draftFilters);
  draftRef.current = draftFilters;

  /** Keeps the same array when nothing changed, so echoes don't rerun every filter. */
  const updateColumnFilters = useCallback((updater: SetStateAction<MRT_ColumnFiltersState>) => {
    setColumnFilters((prev) => {
      const next = typeof updater === 'function' ? updater(prev) : updater;
      return sameColumnFilters(prev, next) ? prev : next;
    });
  }, []);

  const {
    columnVisibility,
    setColumnVisibility,
    columnOrder,
    setColumnOrder,
  } = useTablePersistence('raids', RAIDS_TABLE_PERSISTENCE_DEFAULTS, RAIDS_TABLE_PERSISTENCE_OPTIONS);

  const tableSectionRef = useRef<HTMLDivElement>(null);
  /** The score last filled in for the applied nation; followed while the user hasn't edited it. */
  const autofilledScoreRef = useRef<{ nationId: string; score: string } | null>(null);

  // Live attacker score from PnW (poll while this page is open).
  const {
    data: liveAttacker,
    isError: liveScoreError,
    isFetched: liveScoreFetched,
  } = useQuery({
    queryKey: ['live-nation-score', appliedNationId],
    queryFn: () => fetchLiveNationScore(appliedNationIdNum),
    enabled: appliedNationId !== undefined,
    staleTime: 30_000,
    // A 404 (no such nation) won't change by asking again.
    refetchInterval: (query) =>
      query.state.status === 'error' && !isTransientApiError(query.state.error) ? false : 60_000,
    refetchOnWindowFocus: (query) =>
      query.state.status !== 'error' || isTransientApiError(query.state.error),
    retry: (failureCount, error) => failureCount < 1 && isTransientApiError(error),
  });

  const prevAppliedNationIdRef = useRef(appliedNationId);
  useEffect(() => {
    const prev = prevAppliedNationIdRef.current;
    if (prev === appliedNationId) return;
    prevAppliedNationIdRef.current = appliedNationId;
    // Only clear score when switching between two concrete nations (not initial hydrate).
    if (!prev || !appliedNationId) return;
    autofilledScoreRef.current = null;
    setDraftFilters((prevDraft) =>
      prevDraft.scoreMode === 'yours' && prevDraft.yourScore
        ? { ...prevDraft, yourScore: '' }
        : prevDraft
    );
  }, [appliedNationId]);

  const yourScore = validScore(draftFilters.yourScore);
  // Wait for this nation's score before fetching. Exception: first visit with hydrated yourScore.
  // If live score fails, stop blocking so a default-bounds fetch can still resolve the attacker.
  const yoursScoreUnconfirmed =
    draftFilters.scoreMode === 'yours' &&
    !!appliedNationId &&
    autofilledScoreRef.current?.nationId !== appliedNationId;
  const hasBootstrapYourScore = autofilledScoreRef.current == null && yourScore !== undefined;
  const liveScoreFailed = liveScoreFetched && (liveScoreError || liveAttacker == null);
  const waitingForScoreBounds =
    yoursScoreUnconfirmed && !hasBootstrapYourScore && !liveScoreFailed;
  // 'Your score' with no usable score has no war range to ask for.
  const scoreReady = draftFilters.scoreMode !== 'yours' || yourScore !== undefined;

  /** Score bounds sent to the API (real P&W score from SQLite, not city-count proxy). */
  const apiScoreBounds = useMemo(() => {
    if (draftFilters.scoreMode === 'yours' && yourScore !== undefined) {
      return warRangeQueryBounds(yourScore);
    }
    if (draftFilters.scoreMode === 'yours') {
      return { minScore: MIN_QUERY_SCORE, maxScore: undefined };
    }
    const min = validScore(draftFilters.minScore);
    return {
      minScore: Math.max(MIN_QUERY_SCORE, min ?? MIN_QUERY_SCORE),
      maxScore: validScore(draftFilters.maxScore),
    };
  }, [draftFilters.scoreMode, draftFilters.minScore, draftFilters.maxScore, yourScore]);

  // Fetch raids: API applies score + VM only; everything else is filtered in the table.
  const {
    data,
    isLoading,
    isFetching,
    isPlaceholderData,
    error,
    refetch,
  } = useQuery({
    queryKey: ['raids', appliedNationId, apiScoreBounds.minScore, apiScoreBounds.maxScore],
    queryFn: ({ signal }) => {
      const filters: RaidFilterParams = {
        minScore: apiScoreBounds.minScore,
        maxScore: apiScoreBounds.maxScore,
        vmode: false,
      };
      if (appliedNationId) {
        filters.attackerNationId = appliedNationIdNum;
      }
      return fetchRaids(filters, signal);
    },
    enabled: scoreReady && !waitingForScoreBounds,
    // Keep the current rows on screen (and the table mounted) while a new range loads.
    placeholderData: keepPreviousData,
    retry: (failureCount, err) => failureCount < 1 && isTransientApiError(err),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  /** Prefer live PnW score; only use /api/raids attacker when it matches the applied nation
   * (score-window fallbacks can return a different nation and would thrash yourScore/war-range). */
  const cachedAttackerMatches =
    data?.attacker?.id != null && Number(data.attacker.id) === appliedNationIdNum;
  const effectiveAttackerScore =
    liveAttacker?.score ?? (cachedAttackerMatches ? data?.attacker?.score ?? null : null);
  const effectiveAttackerName =
    liveAttacker?.nationName ??
    (cachedAttackerMatches ? data?.attacker?.nation_name ?? null : null);
  const effectiveAttackerScoreText =
    effectiveAttackerScore != null ? String(effectiveAttackerScore) : '';

  /** Same option list for sidebar MultiSelect and table column (full API list + current picks). */
  const allianceFilterOptions = useMemo(() => {
    const names = new Set<string>();
    for (const t of data?.targets ?? []) {
      const a = String(t.allianceName ?? '').trim();
      if (a && a !== 'None') names.add(a);
    }
    for (const a of [...draftFilters.alliance, ...draftFilters.allianceExclude]) {
      const s = String(a ?? '').trim();
      if (s) names.add(s);
    }
    return Array.from(names).sort((a, b) => a.localeCompare(b));
  }, [data?.targets, draftFilters.alliance, draftFilters.allianceExclude]);

  const positionFilterOptions = useMemo(() => {
    const positions = new Set<string>();
    for (const t of data?.targets ?? []) {
      if (t.alliancePosition) positions.add(t.alliancePosition);
    }
    for (const p of draftFilters.scopeCustomPositions) {
      if (p) positions.add(p);
    }
    const posCol = columnFilterValue(columnFilters, 'alliancePosition');
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

  // Auto-fill yourScore from the live score (else a matching cached one), and keep following
  // it while the field still holds the filled-in value.
  useEffect(() => {
    if (!appliedNationId) {
      autofilledScoreRef.current = null;
      setDraftFilters((prev) => (prev.scoreMode === 'yours' ? { ...prev, scoreMode: 'custom' } : prev));
      return;
    }

    const liveMatches = liveAttacker != null && Number(liveAttacker.id) === appliedNationIdNum;
    let score: number | null = null;
    if (liveMatches) {
      score = liveAttacker.score;
    } else if (liveScoreFailed && cachedAttackerMatches) {
      score = data?.attacker?.score ?? null;
    }
    if (score == null || !Number.isFinite(Number(score))) return;
    const s = String(score);
    const sameAs = (text: string, other: string) =>
      text === other ||
      (validScore(text) !== undefined && Math.abs(Number(text) - Number(other)) < 0.005);

    const filled = autofilledScoreRef.current;
    if (filled?.nationId === appliedNationId) {
      if (filled.score === s) return;
      autofilledScoreRef.current = { nationId: appliedNationId, score: s };
      // The score changed in game: move the war range with it unless the user typed their own.
      setDraftFilters((prev) =>
        sameAs(prev.yourScore, filled.score) ? { ...prev, yourScore: s } : prev
      );
      return;
    }

    autofilledScoreRef.current = { nationId: appliedNationId, score: s };
    setDraftFilters((prev) => {
      const sameScore = sameAs(prev.yourScore, s);
      if (prev.scoreMode === 'custom' && (prev.minScore || prev.maxScore)) {
        return sameScore ? prev : { ...prev, yourScore: s };
      }
      if (prev.scoreMode === 'yours' && sameScore) return prev;
      return { ...prev, yourScore: s, scoreMode: 'yours' };
    });
  }, [
    appliedNationId,
    appliedNationIdNum,
    liveAttacker,
    liveScoreFailed,
    cachedAttackerMatches,
    data?.attacker?.score,
  ]);

  // A mapped filter changed in the table: fold it into the draft. Changes that came from the
  // draft already match it, so only the user's table edits get through.
  useEffect(() => {
    const draft = draftRef.current;
    const fromDraft = buildMappedColumnFiltersFromDraft(draft);
    const changed = Array.from(MAPPED_COLUMN_IDS).filter((id) => {
      // The column filter is disabled while the sidebar excludes alliances.
      if (id === 'allianceName' && draft.allianceMode === 'exclude') return false;
      return !mappedFilterValuesEqual(
        id,
        columnFilterValue(fromDraft, id),
        columnFilterValue(columnFilters, id)
      );
    });
    if (changed.length) {
      setDraftFilters((prev) => applyMappedColumnFilters(prev, columnFilters, changed));
    }
  }, [columnFilters]);

  // The draft drives the URL and the table's mapped filters.
  useEffect(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      writeRaidsDraftToSearchParams(next, draftFilters);
      // Column-filter links were read into the table at load; the table owns them now.
      RAIDS_TABLE_DATA_COLUMN_IDS.forEach((id) => next.delete(id));
      return next;
    }, { replace: true });
    const mapped = buildMappedColumnFiltersFromDraft(draftFilters);
    updateColumnFilters((prev) => [
      ...prev.filter((f) => !MAPPED_COLUMN_IDS.has(f.id)),
      ...mapped,
    ]);
  }, [draftFilters, setSearchParams, updateColumnFilters]);

  useEffect(() => {
    try {
      localStorage.setItem(
        RAIDS_FILTERS_LOCAL_STORAGE_KEY,
        serializeRaidsFiltersStorageV3(draftFilters, columnFilters)
      );
    } catch (error) {
      console.warn('Failed to persist raids filters', error);
    }
  }, [draftFilters, columnFilters]);

  // Only the sidebar rules with no table column run here; the table applies the rest.
  const filteredTargets = useMemo(() => {
    const targets = data?.targets ?? [];
    const excluded =
      draftFilters.allianceMode === 'exclude' && draftFilters.allianceExclude.length > 0
        ? new Set(draftFilters.allianceExclude.map((a) => a.toLowerCase()))
        : null;
    if (!excluded && !draftFilters.performance) return targets;
    return targets.filter(
      (nation) =>
        !(excluded && excluded.has(nation.allianceName.toLowerCase())) &&
        (!draftFilters.performance || isGoodRaidTarget(nation))
    );
  }, [data?.targets, draftFilters.allianceMode, draftFilters.allianceExclude, draftFilters.performance]);

  const resetFilters = useCallback(() => {
    setDraftFilters(
      DEFAULT_RAIDS_DRAFT_FILTERS({
        scoreMode: appliedNationId ? 'yours' : 'custom',
        yourScore: effectiveAttackerScoreText,
      })
    );
  }, [effectiveAttackerScoreText, appliedNationId]);

  const applyNation = useCallback(
    (nationId: string) => {
      setAppliedNationId(nationId);
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set('attackerNationId', nationId);
        return next;
      }, { replace: true });
    },
    [setSearchParams]
  );

  const loginUrl = getDiscordLoginUrl(internalNavPath('/raids', searchParams.toString()));

  // Conditional returns AFTER all hooks

  if (error && !data) {
    return (
      <ErrorState
        title="Failed to load raids"
        message={toApiError(error).message || 'An unexpected error occurred'}
        onRetry={() => refetch()}
      />
    );
  }

  // Disabled while waiting for the new nation's score — treat as loading, not "no data".
  const isInitialLoading = !data && (isLoading || waitingForScoreBounds || !scoreReady);

  if (!data && !isInitialLoading) {
    return <ErrorState title="No data" message="No raid data available" />;
  }

  const setScoreDraft = (patch: Partial<RaidsDraftFilters>) =>
    setDraftFilters((prev) => ({ ...prev, ...patch }));

  const scoreIsDefault =
    draftFilters.scoreMode === (appliedNationId ? 'yours' : 'custom') &&
    draftFilters.yourScore === effectiveAttackerScoreText &&
    !draftFilters.minScore &&
    !draftFilters.maxScore;

  return (
    <Container size="xl" py="md">
      <Stack gap="md">
        {/* Nation Configuration */}
        <Paper withBorder radius="md" p="lg">
          <Stack gap="xs">
            <Group
              justify={isNarrowNationCard ? 'flex-start' : 'space-between'}
              align="flex-start"
              wrap="wrap"
              gap="sm"
            >
              <Group gap="xs" wrap="wrap" align="center">
                <Title order={3} style={{ lineHeight: 1.2 }}>
                  Your Nation
                </Title>
                <Badge color="blue" variant="light">
                  Optional
                </Badge>
              </Group>
              {(effectiveAttackerName || effectiveAttackerScore != null) &&
                appliedNationId &&
                (!isLoading || liveAttacker) && (
                <Group
                  gap="xs"
                  wrap="wrap"
                  align="center"
                  justify={isNarrowNationCard ? 'flex-start' : 'flex-end'}
                  w={isNarrowNationCard ? '100%' : 'auto'}
                  style={{ flex: '1 1 auto', minWidth: 0, maxWidth: '100%' }}
                >
                  <Text
                    size="sm"
                    c="dimmed"
                    style={{ wordBreak: 'break-word', maxWidth: '100%' }}
                  >
                    {effectiveAttackerName}
                  </Text>
                  <Badge variant="light" color="blue" style={{ flexShrink: 0 }}>
                    Score:{' '}
                    {effectiveAttackerScore != null
                      ? effectiveAttackerScore.toFixed(2)
                      : 'N/A'}
                  </Badge>
                </Group>
              )}
            </Group>
            <Text size="sm" c="dimmed">
              Load your nation to pull your score automatically and keep the win% + score range aligned to you.
            </Text>
          </Stack>

          <NationIdField
            label="Nation ID"
            placeholder="Nation ID or Link to Nation"
            size="sm"
            value={appliedNationId ?? ''}
            disableWhenUnchanged
            onEdit={() => {
              nationIdTypedRef.current = true;
            }}
            onSubmit={(raw) => {
              const nationId = normalizeNationId(raw);
              if (!nationId) {
                setNationInputError('Enter a nation ID or a link to a nation.');
                return;
              }
              setNationInputError(null);
              applyNation(nationId);
              // Remember it for users with no saved or linked nation; for everyone else this
              // stays a page-only override of their home nation.
              if (!savedNationId && !linkedNationId) setNationId(nationId);
            }}
            buttonLabel="Load Nation"
            buttonIcon={<IconDownload size={14} />}
            loading={(isLoading || waitingForScoreBounds) && !!appliedNationId}
            inputProps={{ style: { maxWidth: 260 } }}
            errorMessage={nationInputError}
            warningMessage={data?.warning || null}
          />
          {linkedNationId && appliedNationId && appliedNationId !== linkedNationId && (
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
                    applyNation(linkedNationId);
                    setNationId(linkedNationId);
                  }}
                >
                  Use linked nation
                </Button>
              </Stack>
            </Alert>
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
                        <ResetLink onClick={() => setDraftFilters((prev) => ({ ...prev, beige: 'all' }))} />
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
                    <Text size="sm" fw={600}>Hide bad targets</Text>
                    <Text size="xs" c="dimmed">
                      Filters out "bad" targets: nations with negative income, $0 previous beige loot, or (with
                      your nation loaded) a stronger ground force than yours.
                    </Text>
                    <Switch
                      size="sm"
                      label="Hide bad targets"
                      checked={draftFilters.performance}
                      onChange={(event) => {
                        const checked = event.currentTarget.checked;
                        setDraftFilters((prev) => ({ ...prev, performance: checked }));
                      }}
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
                        <ResetLink
                          onClick={() =>
                            setDraftFilters((prev) => ({
                              ...prev,
                              scopeMode: 'preset',
                              scopePreset: 'all',
                              scopeCustomPositions: [],
                            }))
                          }
                        />
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
                        <ResetLink onClick={() => setDraftFilters((prev) => ({ ...prev, maxWars: 'all' }))} />
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
                        onChange={(val) => setDraftFilters((prev) => ({ ...prev, maxWars: val || 'all' }))}
                      />
                      <Text size="sm" c="dimmed">
                        active wars
                      </Text>
                    </Group>
                  </Stack>
                </Paper>
              </Grid.Col>

              <Grid.Col span={{ base: 12, sm: 6, md: 4, lg: 4 }}>
                <PresetOrCustomFilterCard
                  title="Inactivity"
                  description="Presets or a custom minimum (same as table column)."
                  noneValue="none"
                  defaultPreset="3"
                  options={INACTIVE_OPTIONS}
                  customLabel="Custom min days"
                  placeholder="e.g. 10"
                  value={{
                    mode: draftFilters.inactiveMode,
                    preset: draftFilters.inactivePreset,
                    custom: draftFilters.inactiveCustom,
                  }}
                  onChange={(next) =>
                    setDraftFilters((prev) => ({
                      ...prev,
                      inactiveMode: next.mode,
                      inactivePreset: next.preset,
                      inactiveCustom: next.custom,
                    }))
                  }
                />
              </Grid.Col>

              <Grid.Col span={{ base: 12, sm: 6, md: 4, lg: 4 }}>
                <PresetOrCustomFilterCard
                  title="Min Previous Beige Loot"
                  description="Presets or custom min (same parsing as table column)."
                  noneValue="0"
                  defaultPreset="0"
                  options={LOOT_OPTIONS}
                  customLabel="Custom minimum"
                  placeholder="e.g. 5m or 7500000"
                  value={{
                    mode: draftFilters.lootMode,
                    preset: draftFilters.lootPreset,
                    custom: draftFilters.lootCustom,
                  }}
                  onChange={(next) =>
                    setDraftFilters((prev) => ({
                      ...prev,
                      lootMode: next.mode,
                      lootPreset: next.preset,
                      lootCustom: next.custom,
                    }))
                  }
                />
              </Grid.Col>

              <Grid.Col span={{ base: 12, md: 8, lg: 8 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap="xs">
                    <Group gap="xs" justify="space-between">
                      <Text size="sm" fw={600}>Score Range</Text>
                      {!scoreIsDefault && (
                        <ResetLink
                          onClick={() =>
                            setScoreDraft({
                              scoreMode: appliedNationId ? 'yours' : 'custom',
                              yourScore: effectiveAttackerScoreText,
                              minScore: '',
                              maxScore: '',
                            })
                          }
                        />
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">Use your score or set custom limits.</Text>
                    <Select
                      size="sm"
                      data={[
                        { value: 'custom', label: 'Custom min/max' },
                        { value: 'yours', label: 'Based on your score (0.75× – 2.5×)', disabled: !appliedNationId },
                      ]}
                      value={draftFilters.scoreMode}
                      onChange={(val) => setScoreDraft({ scoreMode: val || 'custom' })}
                    />

                    {draftFilters.scoreMode === 'yours' ? (
                      <DebouncedNumberInput
                        size="sm"
                        label="Your Score"
                        placeholder={appliedNationId ? 'Auto-filled from nation' : 'Set nation ID above'}
                        value={draftFilters.yourScore}
                        onCommit={(next) => setScoreDraft({ yourScore: next })}
                        min={0}
                        step={0.01}
                        disabled={!appliedNationId}
                      />
                    ) : (
                      <Grid gutter="sm">
                        <Grid.Col span={6}>
                          <DebouncedNumberInput
                            size="sm"
                            label="Min Score"
                            placeholder="Min"
                            value={draftFilters.minScore}
                            onCommit={(next) => setScoreDraft({ minScore: next })}
                            min={0}
                            step={0.1}
                          />
                        </Grid.Col>
                        <Grid.Col span={6}>
                          <DebouncedNumberInput
                            size="sm"
                            label="Max Score"
                            placeholder="Max"
                            value={draftFilters.maxScore}
                            onCommit={(next) => setScoreDraft({ maxScore: next })}
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
                      <Text size="sm" fw={600}>Alliance Name</Text>
                      {(draftFilters.alliance.length > 0 ||
                        draftFilters.allianceExclude.length > 0 ||
                        draftFilters.allianceMode === 'exclude') && (
                        <ResetLink
                          onClick={() =>
                            setDraftFilters((prev) => ({
                              ...prev,
                              allianceMode: 'include',
                              alliance: [],
                              allianceExclude: [],
                            }))
                          }
                        />
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
                        setDraftFilters((prev) => {
                          const nextMode =
                            (v === 'exclude' ? 'exclude' : 'include') as RaidsDraftFilters['allianceMode'];
                          if (nextMode === prev.allianceMode) return prev;

                          if (nextMode === 'exclude') {
                            return {
                              ...prev,
                              allianceMode: 'exclude',
                              allianceExclude: prev.alliance,
                              alliance: [],
                            };
                          }

                          return {
                            ...prev,
                            allianceMode: 'include',
                            alliance: prev.allianceExclude,
                            allianceExclude: [],
                          };
                        })
                      }
                    />
                    <Text size="xs" c="dimmed">
                      {draftFilters.allianceMode === 'exclude'
                        ? 'Exclude mode hides nations in the alliances you pick. Example: choose Eclipse to remove Eclipse nations from the list.'
                        : 'Include mode shows only nations in the alliances you pick. Example: choose Eclipse to see only Eclipse nations.'}
                    </Text>
                    <MultiSelect
                      size="sm"
                      placeholder={
                        draftFilters.allianceMode === 'exclude'
                          ? 'Select alliances to exclude'
                          : 'Select alliances'
                      }
                      data={allianceFilterOptions}
                      value={
                        draftFilters.allianceMode === 'exclude'
                          ? draftFilters.allianceExclude
                          : draftFilters.alliance
                      }
                      onChange={(val) =>
                        setDraftFilters((prev) =>
                          prev.allianceMode === 'exclude'
                            ? { ...prev, allianceExclude: val }
                            : { ...prev, alliance: val }
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

        {/* Discord: reminders need a sign-in; linking only loads your nation automatically. */}
        {session.status === 'guest' && (
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
                href={loginUrl}
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
        {discordAuthenticated && linkedNationData?.linked === false && (
          <Alert icon={<IconInfoCircle size={16} />} title="Link your nation" color="blue" variant="light">
            <Stack gap="sm" align="flex-start">
              <Text size="sm">
                Link your Politics & War nation to load it here automatically, or use{' '}
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
        <Stack gap="xs" ref={tableSectionRef} style={{ scrollMarginTop: 72 }}>
          <Title order={2}>Raid Targets</Title>
          <Text c="dimmed">
            Find profitable targets to raid. Click a column header to sort by
            that column. Use filters to narrow down results.
          </Text>
        </Stack>

        <JumpToTableButton targetRef={tableSectionRef} />

        {error && data && (
          <Alert color="red" variant="light" title="Couldn't refresh the list">
            <Stack gap="xs" align="flex-start">
              <Text size="sm">
                {toApiError(error).message} The targets below are from the last successful load.
              </Text>
              <Button
                size="xs"
                variant="light"
                color="red"
                leftSection={<IconRefresh size={14} />}
                onClick={() => refetch()}
              >
                Try again
              </Button>
            </Stack>
          </Alert>
        )}

        {/* Table */}
        <Box pos="relative">
          {(isFetching || isPlaceholderData) && !isInitialLoading && (
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
              allianceFilterDisabledReason={
                draftFilters.allianceMode === 'exclude'
                  ? 'Disabled because the sidebar Alliance filter is in Hide (exclude) mode. Switch back to Include only to use this column filter.'
                  : undefined
              }
              positionSelectOptions={positionFilterOptions}
              discordAuthenticated={discordAuthenticated}
              damageAttackerNationId={appliedNationId}
              initialSorting={initialSorting}
              columnVisibility={columnVisibility}
              columnOrder={columnOrder}
              columnFilters={columnFilters}
              onColumnVisibilityChange={setColumnVisibility}
              onColumnOrderChange={setColumnOrder}
              onColumnFiltersChange={updateColumnFilters}
            />
          )}
        </Box>
      </Stack>
    </Container>
  );
}
