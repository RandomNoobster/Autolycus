/**
 * Builds Page
 *
 * Displays city build templates with comprehensive configuration options.
 * Users can import nation data or manually configure infrastructure, land, continent, MMR, etc.
 */

import {
  Container,
  Title,
  Text,
  Stack,
  Group,
  Button,
  Paper,
  NumberInput,
  Select,
  Switch,
  Grid,
  Accordion,
  Tooltip,
  ActionIcon,
  Loader,
  Checkbox,
  ScrollArea,
  Table,
  Badge,
  MultiSelect,
  SegmentedControl,
  SimpleGrid,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import {
  IconInfoCircle,
  IconDownload,
  IconCalculator,
  IconArrowDownRight,
  IconArrowUpRight,
} from '@tabler/icons-react';
import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';

import { fetchNationData, fetchBuilds, fetchGameData } from '@/api/builds';
import { BuildsGrid } from '@/components/builds';
import { ResourceIcon, NationIdField } from '@/components/common';
import type { BuildConfiguration, BuildsResponse, ResourceType, Continent } from '@/types';
import type { GameDataResponse } from '@/types/gameData';
import { CONTINENTS, getContinentRawResources, isResourceValid } from '@/utils/continents';
import { formatNumber } from '@/utils';
import { useNationId } from '@/hooks';

export function BuildsPage() {
  const { nationId: savedNationId, setNationId, parseNationId } = useNationId();
  const [searchParams] = useSearchParams();
  const [showResults, setShowResults] = useState(false);
  const [buildsData, setBuildsData] = useState<BuildsResponse | null>(null);
  const [isLoadingNation, setIsLoadingNation] = useState(false);
  const [isCalculating, setIsCalculating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nationError, setNationError] = useState<string | null>(null);
  const [nationSuccess, setNationSuccess] = useState<string | null>(null);
  const [gameData, setGameData] = useState<GameDataResponse | null>(null);
  const [autoLoadNation, setAutoLoadNation] = useState(false);

  // Load projects and policies on mount
  useEffect(() => {
    const loadGameData = async () => {
      try {
        const data = await fetchGameData();
        setGameData(data);
      } catch (error) {
        console.error('Failed to load game data:', error);
      }
    };
    loadGameData();
  }, []);

  // Form state
  const form = useForm<BuildConfiguration>({
    initialValues: {
      nationId: savedNationId ? parseInt(savedNationId, 10) : undefined,
      infrastructure: 2000,
      land: 1500,
      continent: 'na',
      military: {
        barracks: 5,
        factory: 5,
        airforcebase: 3,
        drydock: 1,
      },
      projects: [],
      policies: [],
      useLiveMarket: true,
      includeMilitaryUpkeep: false,
      militaryUpkeepMode: 'peace',
    },
  });

  // Auto-load nation data from URL
  useEffect(() => {
    const urlNationId = searchParams.get('nationId') || searchParams.get('nation_id');
    if (!urlNationId) return;
    const parsed = parseNationId(urlNationId);
    if (!parsed) return;
    const parsedNum = Number(parsed);
    if (!Number.isFinite(parsedNum) || parsedNum <= 0) return;
    form.setFieldValue('nationId', parsedNum);
    setNationId(parsed);
    setAutoLoadNation(true);
  }, [searchParams, parseNationId, setNationId]);


  const projectOptions = gameData
    ? Object.entries(gameData.projects).map(([key, project]) => ({
        value: key,
        label: project.name,
        description: project.description || 'No description available.',
      }))
    : [];

  const domesticPolicyOptions = gameData
    ? Object.entries(gameData.domesticPolicies).map(([key, policy]) => ({
        value: key,
        label: policy.name,
        description: policy.description || 'No description available.',
      }))
    : [];

  const continentOptions = CONTINENTS.map((continent) => ({
    ...continent,
    rawResources: getContinentRawResources(continent.value),
  }));

  const sanitizeDomesticPolicy = (policy?: string) => {
    if (!policy) return undefined;
    const allowed = Object.keys(gameData?.domesticPolicies ?? {});
    if (!allowed.length) return policy;
    return allowed.includes(policy) ? policy : undefined;
  };

  const handleNationIdChange = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) {
      form.setFieldValue('nationId', undefined);
      return;
    }

    const parsed = Number(trimmed);
    form.setFieldValue('nationId', Number.isNaN(parsed) || parsed <= 0 ? undefined : parsed);
  };

  // Nation data loading
  const handleLoadNation = async () => {
    const nationId = form.values.nationId;
    if (!nationId) return;

    setIsLoadingNation(true);
    setNationError(null);
    setNationSuccess(null);
    try {
      const data = await fetchNationData(nationId);

      // Calculate average infrastructure and land from cities
      const avgInfra = Math.round(
        data.cities.reduce((sum, c) => sum + c.infrastructure, 0) / data.cities.length
      );
      const avgLand = Math.round(
        data.cities.reduce((sum, c) => sum + c.land, 0) / data.cities.length
      );

      // Get military buildings from first city (or average)
      const firstCity = data.cities[0];

      form.setValues({
        ...form.values,
        infrastructure: avgInfra,
        land: avgLand,
        continent: data.continent,
        military: {
          barracks: firstCity.barracks,
          factory: firstCity.factory,
          airforcebase: firstCity.airforcebase,
          drydock: firstCity.drydock,
        },
        projects: data.projects,
        policies: Object.values(data.policies ?? {}),
        domesticPolicy: sanitizeDomesticPolicy(data.policies?.dompolicy),
      });
      setNationError(null);
      setNationSuccess('Nation data loaded successfully');
    } catch (error) {
      console.error('Failed to load nation data:', error);
      const errorMessage = error instanceof Error ? error.message : 'Failed to load nation data';
      setNationError(errorMessage);
      setNationSuccess(null);
    } finally {
      setIsLoadingNation(false);
    }
  };

  useEffect(() => {
    if (!autoLoadNation) return;
    if (!form.values.nationId || isLoadingNation) return;
    handleLoadNation();
    setAutoLoadNation(false);
  }, [autoLoadNation, form.values.nationId, isLoadingNation]);

  // Calculate builds
  const handleCalculate = async () => {
    setError(null);
    setIsCalculating(true);

    try {
      const response = await fetchBuilds({
        ...form.values,
        domesticPolicy: sanitizeDomesticPolicy(form.values.domesticPolicy),
      });
      setBuildsData(response);
      setShowResults(true);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to calculate builds';
      setError(errorMessage);
      console.error('Build calculation error:', err);
    } finally {
      setIsCalculating(false);
    }
  };

  return (
    <Container size="xl" py="xl">
      <Stack gap="xl">
        {/* Header */}
        <div>
          <Title order={1}>City Build Calculator</Title>
          <Text c="dimmed" mt="xs">
            Calculate optimal city builds for maximum resource production based on your nation's stats.
          </Text>
        </div>

        {/* Configuration Form */}
        <Paper p="lg" withBorder radius="md">
          <form onSubmit={form.onSubmit(handleCalculate)}>
            <Stack gap="lg">
              {/* Nation Import Section */}
              <div>
                <Group gap="xs" mb="xs">
                  <Title order={3}>Import Nation Data</Title>
                  <Tooltip label="Load your nation's infrastructure, land, continent, and military buildings automatically">
                    <ActionIcon variant="subtle" size="sm">
                      <IconInfoCircle size={16} />
                    </ActionIcon>
                  </Tooltip>
                </Group>
                <Text size="sm" c="dimmed" mb="md">
                  Enter your nation ID to auto-fill configuration with your current stats.
                </Text>
                <NationIdField
                  placeholder="Nation ID or Link to Nation"
                  size="md"
                  value={form.values.nationId?.toString() ?? ''}
                  onChange={handleNationIdChange}
                  onSubmit={handleLoadNation}
                  buttonLabel="Load Nation"
                  buttonIcon={<IconDownload size={16} />}
                  buttonDisabled={!form.values.nationId}
                  loading={isLoadingNation}
                  inputProps={{ type: 'number', min: 1 }}
                  errorMessage={nationError}
                  successMessage={nationSuccess}
                />
              </div>

              {/* Manual Configuration */}
              <div>
                <Title order={3} mb="md">
                  Manual Configuration
                </Title>

                <Grid gutter="md">
                  {/* Core Stats */}
                  <Grid.Col span={{ base: 12, sm: 6 }}>
                    <Group gap="xs">
                      <NumberInput
                        label="Infrastructure"
                        placeholder="2000"
                        {...form.getInputProps('infrastructure')}
                        min={0}
                        max={5000}
                        style={{ flex: 1 }}
                        required
                      />
                      <Tooltip label="The infrastructure level of your city. Higher infrastructure allows more improvements.">
                        <ActionIcon variant="subtle" size="sm" mt={24}>
                          <IconInfoCircle size={16} />
                        </ActionIcon>
                      </Tooltip>
                    </Group>
                  </Grid.Col>

                  <Grid.Col span={{ base: 12, sm: 6 }}>
                    <Group gap="xs">
                      <NumberInput
                        label="Land"
                        placeholder="1500"
                        {...form.getInputProps('land')}
                        min={0}
                        max={15000}
                        style={{ flex: 1 }}
                        required
                      />
                      <Tooltip label="The amount of land in your city. More land reduces pollution and disease.">
                        <ActionIcon variant="subtle" size="sm" mt={24}>
                          <IconInfoCircle size={16} />
                        </ActionIcon>
                      </Tooltip>
                    </Group>
                  </Grid.Col>

                  {/* Continent */}
                  <Grid.Col span={{ base: 12, sm: 6 }}>
                    <Group gap="xs">
                      <Select
                        label="Continent"
                        placeholder="Select continent"
                        data={continentOptions}
                        {...form.getInputProps('continent')}
                        style={{ flex: 1 }}
                        required
                        searchable
                        maxDropdownHeight={320}
                        renderOption={({ option }) => {
                          const details = option as {
                            label: string;
                            rawResources?: string[];
                          };
                          const rawResources = details.rawResources || [];
                          return (
                            <Stack gap={4}>
                              <Text fw={600} size="sm">
                                {details.label}
                              </Text>
                              <Group gap={6} wrap="wrap">
                                {rawResources.map((resource) => (
                                  <Group key={resource} gap={4} wrap="nowrap">
                                    <ResourceIcon
                                      resource={resource as ResourceType}
                                      showValue={false}
                                      size={16}
                                    />
                                    <Text size="xs" c="dimmed" tt="capitalize">
                                      {resource}
                                    </Text>
                                  </Group>
                                ))}
                              </Group>
                            </Stack>
                          );
                        }}
                      />
                      <Tooltip label="Your nation's continent determines which raw resources you can produce.">
                        <ActionIcon variant="subtle" size="sm" mt={24}>
                          <IconInfoCircle size={16} />
                        </ActionIcon>
                      </Tooltip>
                    </Group>
                  </Grid.Col>

                  {/* MMR - Military Buildings */}
                  <Grid.Col span={12}>
                    <Text size="sm" fw={500} mb="xs">
                      Military Buildings (MMR)
                    </Text>
                    <Grid gutter="sm">
                      <Grid.Col span={{ base: 6, sm: 3 }}>
                        <NumberInput
                          label="Barracks"
                          placeholder="5"
                          {...form.getInputProps('military.barracks')}
                          min={0}
                          max={5}
                        />
                      </Grid.Col>
                      <Grid.Col span={{ base: 6, sm: 3 }}>
                        <NumberInput
                          label="Factories"
                          placeholder="5"
                          {...form.getInputProps('military.factory')}
                          min={0}
                          max={5}
                        />
                      </Grid.Col>
                      <Grid.Col span={{ base: 6, sm: 3 }}>
                        <NumberInput
                          label="Hangars"
                          placeholder="3"
                          {...form.getInputProps('military.airforcebase')}
                          min={0}
                          max={5}
                        />
                      </Grid.Col>
                      <Grid.Col span={{ base: 6, sm: 3 }}>
                        <NumberInput
                          label="Drydocks"
                          placeholder="1"
                          {...form.getInputProps('military.drydock')}
                          min={0}
                          max={3}
                        />
                      </Grid.Col>
                    </Grid>
                  </Grid.Col>
                </Grid>
              </div>

              {/* Advanced Options */}
              <Accordion variant="separated" styles={{ panel: { paddingBottom: 0 } }}>
                <Accordion.Item value="advanced">
                  <Accordion.Control>
                    <Group gap="xs">
                      <Text fw={500}>Advanced Options</Text>
                      <Text size="sm" c="dimmed">
                        (Projects, Policies, Market Prices)
                      </Text>
                    </Group>
                  </Accordion.Control>
                  <Accordion.Panel>
                    <Stack gap="md">
                      {/* Military Upkeep Toggle */}
                      <Group gap="xs">
                        <Switch
                          label="Include Military Upkeep"
                          description="Assume max military units and include their upkeep costs in calculations"
                          {...form.getInputProps('includeMilitaryUpkeep', { type: 'checkbox' })}
                        />
                        <Tooltip label="When enabled, calculations assume you have maximum military units and deduct their upkeep from net income.">
                          <ActionIcon variant="subtle" size="sm">
                            <IconInfoCircle size={16} />
                          </ActionIcon>
                        </Tooltip>
                      </Group>

                      {form.values.includeMilitaryUpkeep && (
                        <Stack gap={4}>
                          <SegmentedControl
                            fullWidth
                            data={[
                              { label: 'Peacetime upkeep', value: 'peace' },
                              { label: 'Wartime upkeep', value: 'war' },
                            ]}
                            value={form.values.militaryUpkeepMode || 'peace'}
                            onChange={(value) =>
                              form.setFieldValue(
                                'militaryUpkeepMode',
                                value as BuildConfiguration['militaryUpkeepMode'],
                              )
                            }
                          />
                          <Text size="xs" c="dimmed">
                            Upkeep is per city. Wartime uses higher P&W upkeep rates; peace uses the lower baseline rates. Default is always peacetime unless you pick wartime.
                          </Text>
                        </Stack>
                      )}

                      {/* Market Data Toggle */}
                      <Group gap="xs" align="flex-start">
                        <Switch
                          label="Use Live Market Prices"
                          description="Switch between live prices and 30d average"
                          {...form.getInputProps('useLiveMarket', { type: 'checkbox' })}
                        />
                        <Tooltip label="Live uses the latest tradeprices tick from the P&W API. 30-day average is the mean of the last 30 tradeprices records (roughly one per day) so spikes are smoothed.">
                          <ActionIcon variant="subtle" size="sm">
                            <IconInfoCircle size={16} />
                          </ActionIcon>
                        </Tooltip>
                      </Group>

                      {gameData && (
                        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
                          <div>
                            <Text size="sm" fw={500} mb="xs">
                              Projects
                            </Text>
                            <Text size="xs" c="dimmed" mb="md">
                              Only projects that change revenue math are shown. Pick the ones you own so the modifiers apply.
                            </Text>
                            <MultiSelect
                              data={projectOptions}
                              value={form.values.projects}
                              onChange={(value) => form.setFieldValue('projects', value)}
                              placeholder="Select revenue-impacting projects"
                              searchable
                              clearable
                              maxDropdownHeight={320}
                              hidePickedOptions={false}
                              renderOption={({ option }) => {
                                const details = option as { label: string; description?: string };
                                return (
                                  <Group align="flex-start" gap="sm" wrap="nowrap">
                                    <Checkbox
                                      checked={form.values.projects.includes(option.value)}
                                      readOnly
                                      tabIndex={-1}
                                    />
                                    <div>
                                      <Text fw={600} size="sm">
                                        {details.label}
                                      </Text>
                                      <Text
                                        size="xs"
                                        c="dimmed"
                                        style={{ whiteSpace: 'normal', lineHeight: 1.35 }}
                                      >
                                        {details.description}
                                      </Text>
                                    </div>
                                  </Group>
                                );
                              }}
                            />
                            <Text size="xs" c="dimmed" mt="xs">
                              Descriptions are included in the dropdown for quick reference.
                            </Text>
                          </div>

                          <div>
                            <Text size="sm" fw={500} mb="xs">
                              Domestic Policy
                            </Text>
                            <Text size="xs" c="dimmed" mb="md">
                              Select the policy you run so the bonus modifiers are baked into the build math.
                            </Text>
                            <Select
                              data={domesticPolicyOptions}
                              value={form.values.domesticPolicy ?? null}
                              onChange={(value) =>
                                form.setFieldValue('domesticPolicy', value ?? undefined)
                              }
                              placeholder="Select a domestic policy"
                              searchable
                              clearable
                              maxDropdownHeight={320}
                              renderOption={({ option }) => {
                                const details = option as { label: string; description?: string };
                                return (
                                  <div>
                                    <Text fw={600} size="sm">
                                      {details.label}
                                    </Text>
                                    <Text
                                      size="xs"
                                      c="dimmed"
                                      style={{ whiteSpace: 'normal', lineHeight: 1.35 }}
                                    >
                                      {details.description}
                                    </Text>
                                  </div>
                                );
                              }}
                            />
                          </div>
                        </SimpleGrid>
                      )}
                    </Stack>
                  </Accordion.Panel>
                </Accordion.Item>
              </Accordion>

              {/* Calculate Button */}
              <Button
                type="submit"
                size="lg"
                leftSection={isCalculating ? <Loader size="xs" /> : <IconCalculator size={20} />}
                fullWidth
                disabled={isCalculating}
              >
                {isCalculating ? 'Calculating...' : 'Calculate Builds'}
              </Button>

              {/* Error Display */}
              {error && (
                <Text c="red" size="sm">
                  Error: {error}
                </Text>
              )}
            </Stack>
          </form>
        </Paper>

        {/* Results */}
        {showResults && buildsData && (
          <Stack gap="lg">
            <Grid gutter="lg" align="stretch">
              <Grid.Col span={{ base: 12, lg: 7, xl: 6 }}>
                <BuildsGrid
                  builds={buildsData.builds}
                  resources={buildsData.resources}
                  land={buildsData.land}
                />
              </Grid.Col>
              <Grid.Col span={{ base: 12, lg: 5, xl: 6 }}>
                {buildsData.prices && (
                  <Paper withBorder radius="md" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                    <Group justify="space-between" align="flex-start" p="md" pb="sm">
                      <Group gap="xs">
                        <Title order={4}>Market Prices</Title>
                        <Tooltip label="Live uses the newest tradeprices tick from the official API. 30-day average is the mean of the last 30 tradeprices records (roughly one per day).">
                          <ActionIcon variant="subtle" size="sm">
                            <IconInfoCircle size={16} />
                          </ActionIcon>
                        </Tooltip>
                      </Group>
                      <Badge color={buildsData.prices.mode === 'live' ? 'green' : 'yellow'}>
                        {buildsData.prices.mode === 'live' ? 'USING LIVE PRICES' : 'USING 30 DAY AVERAGE'}
                      </Badge>
                    </Group>
                    <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', paddingLeft: 'var(--mantine-spacing-md)', paddingRight: 'var(--mantine-spacing-md)', paddingBottom: 'var(--mantine-spacing-md)' }}>
                      <PriceTable prices={buildsData.prices} />
                    </div>
                  </Paper>
                )}
              </Grid.Col>
            </Grid>

            <Grid gutter="lg" align="stretch">
              {(() => {
                const sampleKey = buildsData.resources.find((resource) => resource === 'net income')
                  ?? buildsData.resources[0];
                const sampleBuild = sampleKey ? buildsData.builds[sampleKey] : undefined;
                if (!sampleBuild?.unitUpkeep) return null;
                const unitOrder = ['soldiers', 'tanks', 'aircraft', 'ships'];
                const unitLabels: Record<string, string> = {
                  soldiers: 'Soldiers',
                  tanks: 'Tanks',
                  aircraft: 'Planes',
                  ships: 'Ships',
                };
                const priceSource =
                  buildsData.prices?.mode === 'live'
                    ? buildsData.prices?.live ?? {}
                    : buildsData.prices?.average30d ?? buildsData.prices?.live ?? {};
                const foodPrice = priceSource?.food || 0;

                const modes = sampleBuild.unitUpkeep.modes || {
                  peace: {
                    total: sampleBuild.unitUpkeep.total,
                    food: sampleBuild.unitUpkeep.food,
                    breakdown: sampleBuild.unitUpkeep.breakdown,
                  },
                  war: {
                    total: sampleBuild.unitUpkeep.total,
                    food: sampleBuild.unitUpkeep.food,
                    breakdown: sampleBuild.unitUpkeep.breakdown,
                  },
                };
                const activeMode = sampleBuild.unitUpkeep.mode || 'peace';
                const active = modes[activeMode] || {
                  total: sampleBuild.unitUpkeep.total,
                  food: sampleBuild.unitUpkeep.food,
                  breakdown: sampleBuild.unitUpkeep.breakdown,
                };
                const activeTotal = active.total ?? 0;
                const activeFood = active.food ?? 0;
                const netUpkeep = activeTotal + activeFood * foodPrice;

                return (
                  <>
                    <Grid.Col span={{ base: 12, md: 8 }}>
                      <Paper withBorder p="md" radius="md">
                      <Group justify="space-between" mb="xs">
                        <Title order={4}>Unit Upkeep</Title>
                        <Badge color={sampleBuild.unitUpkeep.included ? 'green' : 'gray'}>
                          {sampleBuild.unitUpkeep.included ? 'Included in totals' : 'Not included'}
                        </Badge>
                      </Group>
                      <Text size="sm" c="dimmed" mb="sm">
                        Per-city upkeep for the max units allowed by {form.values.military.barracks}/{form.values.military.factory}/{form.values.military.airforcebase}/{form.values.military.drydock} MMR. Using {activeMode} rates{sampleBuild.unitUpkeep.selectedMode ? ` (${sampleBuild.unitUpkeep.selectedMode} preference)` : ''}.
                      </Text>
                      <Grid gutter="sm" mb="sm">
                        {(['peace', 'war'] as const).map((mode) => {
                          const modeData = modes[mode];
                          if (!modeData) return null;
                          const totalWithFood = (modeData.total ?? 0) + (modeData.food ?? 0) * foodPrice;
                          const isActive = activeMode === mode;
                          return (
                            <Grid.Col span={{ base: 12, md: 6 }} key={mode}>
                              <Paper
                                withBorder
                                p="xs"
                                radius="sm"
                                style={{
                                  opacity: isActive ? 1 : 0.55,
                                  transition: 'opacity 0.2s ease',
                                }}
                              >
                                <Group justify="space-between" mb={4}>
                                  <Text fw={600} c={isActive ? undefined : 'dimmed'}>
                                    {mode === 'peace' ? 'Peacetime' : 'Wartime'}
                                  </Text>
                                  {isActive && (
                                    <Badge
                                      size="xs"
                                      color={mode === 'peace' ? 'teal' : 'orange'}
                                      variant="light"
                                    >
                                      Active
                                    </Badge>
                                  )}
                                </Group>
                                <Text size="sm" c={isActive ? undefined : 'dimmed'}>
                                  Money: ${formatNumber(modeData.total ?? 0)}
                                </Text>
                                <Text size="sm" c={isActive ? undefined : 'dimmed'}>
                                  Food: {formatNumber(modeData.food ?? 0, 2)} /turn
                                </Text>
                                <Text size="sm" c="dimmed">
                                  Money + food @ prices: ${formatNumber(totalWithFood, 2)}
                                </Text>
                              </Paper>
                            </Grid.Col>
                          );
                        })}
                      </Grid>

                      <Paper withBorder p="sm" radius="sm" mb="sm">
                        <Text fw={600} size="sm" mb="xs">
                          Per-unit breakdown ({activeMode === 'peace' ? 'Peacetime' : 'Wartime'})
                        </Text>
                        <Grid gutter="sm">
                          {unitOrder.map((unit) => {
                            const value = active.breakdown?.[unit] || 0;
                            const count = sampleBuild.unitUpkeep?.counts[unit] || 0;
                            return (
                              <Grid.Col span={{ base: 6, md: 3 }} key={unit}>
                                <Paper withBorder p="xs" radius="sm">
                                  <Text fw={600}>{unitLabels[unit]}</Text>
                                  <Text size="sm">{formatNumber(count)} units</Text>
                                  <Text size="sm" c="dimmed">${formatNumber(value)}</Text>
                                </Paper>
                              </Grid.Col>
                            );
                          })}
                        </Grid>
                        <Group justify="space-between" mt="sm">
                          <div>
                            <Text fw={600}>Money: ${formatNumber(active.total ?? 0)}</Text>
                            <Text fw={600}>Food: {formatNumber(active.food ?? 0, 2)} /turn</Text>
                            <Text fw={700} size="lg">Net (including food): ${formatNumber(netUpkeep, 2)}</Text>
                          </div>
                        </Group>
                      </Paper>
                    </Paper>
                    </Grid.Col>
                    <Grid.Col span={{ base: 12, md: 4 }}>
                      <ContinentRestrictionsPanel
                        resources={buildsData.resources}
                        continent={form.values.continent}
                        foodModifiers={buildsData.foodModifiers}
                      />
                    </Grid.Col>
                  </>
                );
              })()}
            </Grid>
          </Stack>
        )}
      </Stack>
    </Container>
  );
}

function ContinentRestrictionsPanel({
  resources,
  continent,
  foodModifiers,
}: {
  resources: string[];
  continent: Continent;
  foodModifiers?: BuildsResponse['foodModifiers'];
}) {
  const invalidResources = resources.filter((resource) => !isResourceValid(resource, continent));

  return (
    <Paper withBorder radius="md" p="md">
      <Group gap="xs" mb="xs" align="center" wrap="wrap">
        <Title order={4}>Continent Resource Modifiers</Title>
      </Group>
      {invalidResources.length > 0 ? (
        <>
          <Text size="sm" c="dimmed" mb="sm">
            These raws cannot be produced on your selected continent. Swap continents to use these templates.
          </Text>
          <Group gap="sm" wrap="wrap">
            {invalidResources.map((resource) => (
              <Paper key={resource} withBorder p="xs" radius="sm" shadow="xs">
                <Group gap={6} align="center">
                  <ResourceIcon resource={resource as ResourceType} showValue={false} size={18} />
                  <Text tt="capitalize" fw={600} size="sm">
                    {resource}
                  </Text>
                </Group>
              </Paper>
            ))}
          </Group>
          <Text size="xs" c="dimmed" mt="xs">
            Manufactured resources remain available everywhere; only raw resource slots are continent-locked.
          </Text>
        </>
      ) : (
        <Text size="sm" c="dimmed">
          All raw resources referenced by these templates are available on your selected continent.
        </Text>
      )}

      {foodModifiers && (
        <Paper withBorder p="sm" radius="sm" mt="md">
          <Group gap="xs" mb="xs" align="center">
            <ResourceIcon resource="food" showValue={false} size={20} />
            <Text fw={600} size="sm">Food Production Modifiers</Text>
          </Group>
          <Stack gap={4}>
            <Group justify="space-between">
              <Text size="sm" c="dimmed">Seasonal:</Text>
              <Text size="sm" fw={500}>{((foodModifiers.seasonal - 1) * 100).toFixed(1)}%</Text>
            </Group>
            <Group justify="space-between">
              <Text size="sm" c="dimmed">Radiation:</Text>
              <Text size="sm" fw={500}>{((foodModifiers.radiationMultiplier - 1) * 100).toFixed(1)}%</Text>
            </Group>
            <Group justify="space-between">
              <Text size="sm" c="dimmed" fw={600}>Combined:</Text>
              <Text size="sm" fw={600}>{((foodModifiers.combinedFoodMultiplier - 1) * 100).toFixed(1)}%</Text>
            </Group>
          </Stack>
        </Paper>
      )}
    </Paper>
  );
}

type PricePayload = NonNullable<BuildsResponse['prices']>;

function PriceTable({ prices }: { prices: PricePayload }) {
  const live = prices.live || {};
  const avg = prices.average30d || {};
  const rows = Object.keys({ ...live, ...avg }).sort();

  const formatDiff = (resource: string) => {
    const liveVal = live[resource];
    const avgVal = avg[resource];
    if (!liveVal || !avgVal) return null;
    const diff = ((liveVal - avgVal) / avgVal) * 100;
    const isUp = diff >= 0;
    const Icon = isUp ? IconArrowUpRight : IconArrowDownRight;
    const color = isUp ? 'green' : 'red';
    return (
      <Group gap={4} c={color}>
        <Icon size={14} />
        <Text size="sm" c={color}>{diff.toFixed(1)}%</Text>
      </Group>
    );
  };

  return (
    <>
      <ScrollArea.Autosize type="auto" offsetScrollbars>
        <Table striped withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Resource</Table.Th>
              <Table.Th>Live</Table.Th>
              <Table.Th>30 Day Average</Table.Th>
              <Table.Th>Live Deviation from Average</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((resource) => (
              <Table.Tr key={resource}>
                <Table.Td>
                  <Group gap="xs">
                    <ResourceIcon resource={resource as ResourceType} size={16} />
                    <Text style={{ textTransform: 'capitalize' }}>{resource}</Text>
                  </Group>
                </Table.Td>
                <Table.Td>${formatNumber(live[resource] ?? 0, 2)}</Table.Td>
                <Table.Td>${formatNumber(avg[resource] ?? 0, 2)}</Table.Td>
                <Table.Td>{formatDiff(resource)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollArea.Autosize>
      <Text size="xs" c="dimmed" mt="xs">
        Prices come from the P&W GraphQL tradeprices feed; the 30-day average is the mean of the last 30 entries.
      </Text>
    </>
  );
}
