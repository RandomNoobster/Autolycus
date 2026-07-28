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
import { getLinkedNation } from '@/api/auth';
import { ErrorState, NationIdField } from '@/components/common';
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

  const { data: linkedNationData } = useQuery({
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

  const urlAttackerId = searchParams.get('attackerNationId') || savedNationId || '';
  const [draftNationId, setDraftNationId] = useState(urlAttackerId);
  const [appliedNationId, setAppliedNationId] = useState(urlAttackerId);

  const urlAttrition = parseOptionalBoolParam(searchParams, 'attrition');
  const urlGuidingSatellite = parseOptionalBoolParam(searchParams, 'guidingSatellite');
  const [attritionEnabled, setAttritionEnabled] = useState<boolean>(urlAttrition ?? true);
  const [guidingSatelliteEnabled, setGuidingSatelliteEnabled] = useState<boolean>(
    urlGuidingSatellite ?? false
  );
  /** Nation id we already preset (or URL-overrode) damage mods for. */
  const damageModsPresetForNationRef = useRef<string | null>(
    urlAttackerId && (urlAttrition !== null || urlGuidingSatellite !== null)
      ? urlAttackerId
      : null
  );

  const [draftFilters, setDraftFilters] = useState<NukeTargetsDraftFilters>(() =>
    buildNukeTargetsDraftFromSearchParams(searchParams, urlAttackerId || undefined, '')
  );

  const filtersRestoredRef = useRef(false);
  /**
   * After hydrating from localStorage, draft URL sync + persist effects must not run in the same
   * passive effect pass as the restore: they would still see the pre-restore draft and overwrite
   * the URL / localStorage with defaults.
   */
  const suppressDraftUrlSyncAndPersistRef = useRef(false);
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
      return;
    }

    const stored = parseNukeTargetsFiltersStorage(
      localStorage.getItem(NUKE_TARGETS_FILTER_STORAGE_KEY),
      nationKey
    );
    if (!stored) {
      filtersRestoredRef.current = true;
      return;
    }

    suppressDraftUrlSyncAndPersistRef.current = true;
    setDraftFilters(stored);
    setSearchParams((prev) => writeNukeDraftToSearchParams(prev, stored), { replace: true });
    filtersRestoredRef.current = true;
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
    setDraftFilters((prev) => (nukeDraftsEqual(prev, fromUrl) ? prev : fromUrl));
    // Only re-hydrate when the query string changes — not when nation id alone updates.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- searchParamsKey tracks searchParams
  }, [searchParamsKey]);

  useEffect(() => {
    if (savedNationId && !appliedNationId) {
      setAppliedNationId(savedNationId);
      setDraftNationId(savedNationId);
    }
  }, [savedNationId, appliedNationId]);

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

  const apiScoreBounds = useMemo(() => {
    if (appliedFilters.scoreMode === 'yours' && appliedNationId) {
      const score = parseNumericValue(appliedFilters.yourScore);
      if (score > 0) {
        return warRangeQueryBounds(score);
      }
    }
    const min = parseNumericValue(appliedFilters.minScore);
    const max = parseNumericValue(appliedFilters.maxScore);
    return {
      minScore: min > 0 ? min : 15,
      maxScore: max > 0 ? max : undefined,
    };
  }, [appliedFilters, appliedNationId]);

  const { data, error, isLoading, isFetching, refetch } = useQuery({
    queryKey: [
      'nuke-targets',
      appliedNationId,
      apiScoreBounds.minScore,
      apiScoreBounds.maxScore,
      attritionEnabled,
      guidingSatelliteEnabled,
    ],
    queryFn: () =>
      fetchNukeTargets({
        attackerNationId: appliedNationId ? Number(appliedNationId) : undefined,
        minScore: apiScoreBounds.minScore,
        maxScore: apiScoreBounds.maxScore,
        vmode: false,
        attrition: attritionEnabled,
        guidingSatellite: guidingSatelliteEnabled,
      }),
    enabled: !!appliedNationId,
    retry: false,
  });

  const isInitialLoading = isLoading && !!appliedNationId;

  useEffect(() => {
    if (!appliedNationId) {
      damageModsPresetForNationRef.current = null;
      return;
    }
    if (!data?.attacker) return;
    if (damageModsPresetForNationRef.current === appliedNationId) return;
    damageModsPresetForNationRef.current = appliedNationId;
    setAttritionEnabled(data.attacker.warpolicy === 'Attrition');
    setGuidingSatelliteEnabled(Boolean(data.attacker.guidingSatellite));
  }, [data?.attacker, appliedNationId]);

  useEffect(() => {
    if (!appliedNationId) return;
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set('attrition', attritionEnabled ? 'true' : 'false');
        next.set('guidingSatellite', guidingSatelliteEnabled ? 'true' : 'false');
        if (next.toString() === prev.toString()) return prev;
        return next;
      },
      { replace: true }
    );
  }, [appliedNationId, attritionEnabled, guidingSatelliteEnabled, setSearchParams]);

  useEffect(() => {
    if (data?.attacker?.score && appliedNationId) {
      const s = data.attacker.score.toString();
      setDraftFilters((prev) => {
        if (prev.scoreMode === 'yours' && prev.yourScore === s) return prev;
        return { ...prev, yourScore: s, scoreMode: 'yours' };
      });
    } else if (!appliedNationId) {
      setDraftFilters((prev) => (prev.scoreMode !== 'yours' ? prev : { ...prev, scoreMode: 'custom' }));
    }
  }, [data?.attacker?.score, appliedNationId]);

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
    const nationScore = data?.attacker?.score?.toString() || '';
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
  }, [appliedNationId, data?.attacker?.score, setSearchParams]);

  if (error) {
    const apiError = error as unknown as ApiError;
    return (
      <ErrorState
        title="Failed to load nuke targets"
        message={apiError.message || 'An unexpected error occurred'}
        onRetry={() => refetch()}
      />
    );
  }

  const attackerPolicy = data?.attacker?.warpolicy || '';

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
              {data?.attacker && appliedNationId && !isLoading && (
                <Group
                  gap="xs"
                  wrap="wrap"
                  align="center"
                  justify={isNarrowNationCard ? 'flex-start' : 'flex-end'}
                  w={isNarrowNationCard ? '100%' : 'auto'}
                  style={{ flex: '1 1 auto', minWidth: 0, maxWidth: '100%' }}
                >
                  <Text size="sm" c="dimmed" style={{ wordBreak: 'break-word', maxWidth: '100%' }}>
                    {data.attacker.nation_name}
                  </Text>
                  <Badge variant="light" color="blue" style={{ flexShrink: 0 }}>
                    Score: {data.attacker.score?.toFixed(2) || 'N/A'}
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
              value={draftNationId}
              onChange={setDraftNationId}
              onSubmit={() => {
                const parsed = parseNationId(draftNationId);
                if (parsed) {
                  setAppliedNationId(parsed);
                  setDraftNationId(parsed);
                  setNationId(parsed);
                  damageModsPresetForNationRef.current = null;
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
              buttonDisabled={!draftNationId || draftNationId === appliedNationId}
              loading={isLoading && !!appliedNationId}
              inputProps={{ style: { maxWidth: 260 } }}
              warningMessage={data?.warning || null}
            />
            {appliedNationId && data?.attacker && !isLoading ? (
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
                  checked={attritionEnabled}
                  onChange={(event) => {
                    damageModsPresetForNationRef.current = appliedNationId;
                    setAttritionEnabled(event.currentTarget.checked);
                  }}
                />
                <Switch
                  label="Guiding Satellite"
                  description="+20% missile and nuke infrastructure damage."
                  checked={guidingSatelliteEnabled}
                  onChange={(event) => {
                    damageModsPresetForNationRef.current = appliedNationId;
                    setGuidingSatelliteEnabled(event.currentTarget.checked);
                  }}
                />
              </Stack>
            ) : null}
            {linkedNationId && appliedNationId && appliedNationId !== linkedNationId && (
              <Alert color="yellow" variant="light" title="Temporary Override" mt="sm">
                You are currently overriding your linked nation ({linkedNationId}) for this page.
              </Alert>
            )}
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
                        const defaultScore = data?.attacker?.score?.toString() || '';
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
                            const nationScore = data?.attacker?.score?.toString() || '';
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
                disabled={isLoading}
              >
                Reset All
              </Button>
            </Group>
          </Stack>
        </Paper>

        <Stack gap="xs">
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

        {!appliedNationId ? (
          <Paper withBorder p="xl" radius="md">
            <Text ta="center" c="dimmed">
              Load your nation above to view the target table with damage calculations.
            </Text>
          </Paper>
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
