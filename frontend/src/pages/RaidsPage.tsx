/**
 * Raids Page
 *
 * Displays raid targets with secure token authentication.
 */

import {
  Container,
  Title,
  Text,
  Stack,
  Group,
  Badge,
  Card,
  Grid,
  NumberInput,
  Select,
  Switch,
  Button,
  Tooltip,
  ActionIcon,
  Autocomplete,
  Anchor,
} from '@mantine/core';
import { useState, useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { IconClock, IconQuestionMark, IconSearch, IconX } from '@tabler/icons-react';
import { useDebouncedValue } from '@mantine/hooks';

import { fetchRaids, searchAlliances } from '@/api';
import { useUrlParams } from '@/hooks';
import { RaidsTable } from '@/components/raids';
import { TokenError, LoadingState, ErrorState } from '@/components/common';
import type { ApiError } from '@/types';

export function RaidsPage() {
  const { token, initialColumnFilters, initialSorting } = useUrlParams();
  const [searchParams, setSearchParams] = useSearchParams();

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
    alliance: searchParams.get('alliance') || undefined,
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
    alliance: activeFilters.alliance || '',
    beige: activeFilters.beige === true ? 'only' : activeFilters.beige === false ? 'hide' : 'all',
    maxWars: activeFilters.maxWars?.toString() || 'all',
    inactiveMinDays: activeFilters.inactiveMinDays?.toString() || 'none',
    scope: activeFilters.scope || 'all',
    minBeigeLoot: activeFilters.minBeigeLoot?.toString() || '0',
    performance: activeFilters.performance ?? false,
    scoreMode: activeFilters.scoreMode || 'yours',
    yourScore: activeFilters.yourScore?.toString() || '',
    minScore: activeFilters.minScore?.toString() || '',
    maxScore: activeFilters.maxScore?.toString() || '',
  });

  // Alliance autocomplete
  const [allianceQuery, setAllianceQuery] = useState(activeFilters.alliance || '');
  const [debouncedAllianceQuery] = useDebouncedValue(allianceQuery, 300);
  const { data: allianceOptions = [] } = useQuery({
    queryKey: ['alliance-search', token, debouncedAllianceQuery],
    queryFn: () => debouncedAllianceQuery.length >= 2 && token ? searchAlliances(token, debouncedAllianceQuery, 15) : Promise.resolve([]),
    enabled: !!token && debouncedAllianceQuery.length >= 2,
  });

  // Fetch raids data - must be before any conditional returns
  const {
    data,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['raids', token],
    queryFn: () => fetchRaids(token || '', {}),
    retry: false,
    enabled: !!token,
  });

  // Apply filters locally in the browser - must be before conditional returns
  const filteredTargets = useMemo(() => {
    if (!data?.targets) return [];
    
    let filtered = [...data.targets];

    // Alliance filter
    if (activeFilters.alliance) {
      const query = activeFilters.alliance.toLowerCase();
      filtered = filtered.filter(nation => 
        nation.allianceName.toLowerCase().includes(query)
      );
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

  const resetFilters = useCallback(() => {
    setDraftFilters({
      alliance: '',
      beige: 'all',
      maxWars: 'all',
      inactiveMinDays: 'none',
      scope: 'all',
      minBeigeLoot: '0',
      performance: false,
      scoreMode: 'yours',
      yourScore: '',
      minScore: '',
      maxScore: '',
    });
    setAllianceQuery('');
  }, []);

  const applyFilters = () => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      
      // Clear old filter params
      ['alliance', 'beige', 'maxWars', 'inactiveMinDays', 'scope', 'minBeigeLoot', 'performance', 'scoreMode', 'yourScore', 'minScore', 'maxScore'].forEach(k => next.delete(k));
      
      // Apply new filters
      if (draftFilters.alliance) next.set('alliance', draftFilters.alliance);
      
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
        }
      } else if (draftFilters.scoreMode === 'custom') {
        if (draftFilters.minScore) next.set('minScore', draftFilters.minScore);
        if (draftFilters.maxScore) next.set('maxScore', draftFilters.maxScore);
        next.set('scoreMode', 'custom');
      }
      
      return next;
    }, { replace: true });
  };

  // Conditional returns AFTER all hooks
  if (!token) {
    return <TokenError type="missing" />;
  }

  if (isLoading) {
    return <LoadingState message="Loading raid targets, this may take some time..." />;
  }

  if (error) {
    const apiError = error as unknown as ApiError;
    
    if (apiError.code === 'TOKEN_EXPIRED') {
      return <TokenError type="expired" message={apiError.message} />;
    }
    if (apiError.code === 'TOKEN_INVALID') {
      return <TokenError type="invalid" message={apiError.message} />;
    }
    
    return (
      <ErrorState
        title="Failed to load raids"
        message={apiError.message || 'An unexpected error occurred'}
        onRetry={() => refetch()}
      />
    );
  }

  if (!data) {
    return <ErrorState title="No data" message="No raid data available" />;
  }

  return (
    <Container size="xl" py="md">
      <Stack gap="md">
        <Card withBorder shadow="xs">
          <Stack gap="md">
            <Title order={4}>Filters</Title>
            <Grid gutter="md">
              <Grid.Col span={{ base: 12, md: 6 }}>
                <Stack gap={4}>
                  <Group gap="xs" justify="space-between">
                    <Text size="sm" fw={500}>Beige Status</Text>
                    {draftFilters.beige !== 'all' && (
                      <Anchor size="xs" onClick={() => setDraftFilters(prev => ({ ...prev, beige: 'all' }))}>
                        reset
                      </Anchor>
                    )}
                  </Group>
                  <Select
                    data={[
                      { value: 'all', label: 'Show all nations' },
                      { value: 'only', label: 'Only beige nations' },
                      { value: 'hide', label: 'Hide beige nations' },
                    ]}
                    value={draftFilters.beige}
                    onChange={(val) => setDraftFilters(prev => ({ ...prev, beige: val || 'all' }))}
                  />
                </Stack>
              </Grid.Col>
              
              <Grid.Col span={{ base: 12, md: 6 }}>
                <Stack gap={4}>
                  <Group gap="xs" justify="space-between">
                    <Text size="sm" fw={500}>Alliance Name</Text>
                    {draftFilters.alliance && (
                      <Anchor size="xs" onClick={() => {
                        setAllianceQuery('');
                        setDraftFilters(prev => ({ ...prev, alliance: '' }));
                      }}>
                        reset
                      </Anchor>
                    )}
                  </Group>
                  <Autocomplete
                    placeholder="Search by name, acronym, or ID..."
                    value={allianceQuery}
                    onChange={(val) => {
                      setAllianceQuery(val);
                      setDraftFilters(prev => ({ ...prev, alliance: val }));
                    }}
                    data={allianceOptions.map(a => a.label)}
                    limit={15}
                    onOptionSubmit={(val) => {
                      // Extract the alliance name from "Name [Acronym]" format
                      const match = val.match(/^(.+?)\s*\[/);
                      const allianceName = match ? match[1] : val;
                      setAllianceQuery(allianceName);
                      setDraftFilters(prev => ({ ...prev, alliance: allianceName }));
                    }}
                  />
                </Stack>
              </Grid.Col>

              <Grid.Col span={{ base: 12, md: 6 }}>
                <Stack gap={4}>
                  <Group gap="xs" justify="space-between">
                    <Text size="sm" fw={500}>Alliance Membership</Text>
                    {draftFilters.scope !== 'all' && (
                      <Anchor size="xs" onClick={() => setDraftFilters(prev => ({ ...prev, scope: 'all' }))}>
                        reset
                      </Anchor>
                    )}
                  </Group>
                  <Select
                    data={[
                      { value: 'all', label: 'All nations' },
                      { value: 'apps_or_none', label: 'Applicants + No alliance' },
                      { value: 'no_alliance', label: 'No alliance only' },
                    ]}
                    value={draftFilters.scope}
                    onChange={(val) => setDraftFilters(prev => ({ ...prev, scope: (val || 'all') as 'all' | 'apps_or_none' | 'no_alliance' }))}
                  />
                </Stack>
              </Grid.Col>

              <Grid.Col span={{ base: 12, md: 6 }}>
                <Stack gap={4}>
                  <Group gap="xs" justify="space-between">
                    <Text size="sm" fw={500}>Defensive Wars</Text>
                    {draftFilters.maxWars !== 'all' && (
                      <Anchor size="xs" onClick={() => setDraftFilters(prev => ({ ...prev, maxWars: 'all' }))}>
                        reset
                      </Anchor>
                    )}
                  </Group>
                  <Group gap="xs" align="center" wrap="nowrap">
                    <Select
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
              </Grid.Col>

              <Grid.Col span={{ base: 12, md: 6 }}>
                <Stack gap={4}>
                  <Group gap="xs" justify="space-between">
                    <Text size="sm" fw={500}>Inactivity</Text>
                    {draftFilters.inactiveMinDays !== 'none' && (
                      <Anchor size="xs" onClick={() => setDraftFilters(prev => ({ ...prev, inactiveMinDays: 'none' }))}>
                        reset
                      </Anchor>
                    )}
                  </Group>
                  <Group gap="xs" align="center" wrap="nowrap">
                    <Select
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
              </Grid.Col>

              <Grid.Col span={{ base: 12, md: 6 }}>
                <Stack gap={4}>
                  <Group gap="xs" justify="space-between">
                    <Text size="sm" fw={500}>Min Previous Beige Loot</Text>
                    {draftFilters.minBeigeLoot !== '0' && (
                      <Anchor size="xs" onClick={() => setDraftFilters(prev => ({ ...prev, minBeigeLoot: '0' }))}>
                        reset
                      </Anchor>
                    )}
                  </Group>
                  <Select
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
              </Grid.Col>

              <Grid.Col span={12}>
                <Stack gap="xs">
                  <Group gap="xs" justify="space-between">
                    <Text size="sm" fw={500}>Score Range</Text>
                    {(draftFilters.scoreMode !== 'yours' || draftFilters.yourScore || draftFilters.minScore || draftFilters.maxScore) && (
                      <Anchor size="xs" onClick={() => setDraftFilters(prev => ({ ...prev, scoreMode: 'yours', yourScore: '', minScore: '', maxScore: '' }))}>
                        reset
                      </Anchor>
                    )}
                  </Group>
                  <Select
                    data={[
                      { value: 'custom', label: 'Custom min/max' },
                      { value: 'yours', label: 'Based on your score (0.75x - 2.5x)' },
                    ]}
                    value={draftFilters.scoreMode}
                    onChange={(val) => setDraftFilters(prev => ({ ...prev, scoreMode: val || 'yours' }))}
                  />
                  
                  {draftFilters.scoreMode === 'yours' ? (
                    <NumberInput
                      label="Your Score"
                      placeholder="Enter your nation score"
                      value={draftFilters.yourScore}
                      onChange={(val) => setDraftFilters(prev => ({ ...prev, yourScore: val?.toString() || '' }))}
                      min={0}
                      step={0.01}
                    />
                  ) : (
                    <Grid gutter="sm">
                      <Grid.Col span={6}>
                        <NumberInput
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
              </Grid.Col>

              <Grid.Col span={12}>
                <Group gap="xs">
                  <Switch
                    label="Performance Filter"
                    checked={draftFilters.performance}
                    onChange={(event) =>
                      setDraftFilters(prev => ({ ...prev, performance: event.currentTarget.checked }))
                    }
                  />
                  <Tooltip
                    label='Filters out "bad" targets: nations with negative income, stronger ground force than you, or $0 previous beige loot'
                    multiline
                    w={250}
                  >
                    <ActionIcon size="sm" variant="subtle" color="gray">
                      <IconQuestionMark size={14} />
                    </ActionIcon>
                  </Tooltip>
                </Group>
              </Grid.Col>

              <Grid.Col span={12}>
                <Group gap="sm">
                  <Button
                    leftSection={<IconSearch size={16} />}
                    onClick={applyFilters}
                    style={{ flex: 1 }}
                  >
                    Apply Filters
                  </Button>
                  <Button
                    leftSection={<IconX size={16} />}
                    onClick={resetFilters}
                    variant="light"
                    color="gray"
                    style={{ flex: 1 }}
                  >
                    Reset All
                  </Button>
                </Group>
              </Grid.Col>
            </Grid>
          </Stack>
        </Card>

        {/* Header */}
        <Group justify="space-between" align="flex-start">
          <Stack gap="xs">
            <Title order={2}>Raid Targets</Title>
            <Text c="dimmed">
              Find profitable targets to raid. Click column headers to sort,
              use filters to narrow down results.
            </Text>
          </Stack>
          <Badge
            leftSection={<IconClock size={12} />}
            variant="light"
            color="gray"
          >
            Generated: {new Date(data.generatedAt).toLocaleString()}
          </Badge>
        </Group>

        {/* Table */}
        <RaidsTable
          data={filteredTargets}
          token={token}
          showBeige={data.showBeige}
          initialFilters={initialColumnFilters}
          initialSorting={initialSorting}
        />
      </Stack>
    </Container>
  );
}
