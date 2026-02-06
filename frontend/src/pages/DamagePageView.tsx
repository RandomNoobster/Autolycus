/**
 * Damage Page
 *
 * Displays damage calculator with charts and tables (public page, no authentication required).
 */

import {
  Container,
  Title,
  Text,
  Stack,
  Group,
  Paper,
  Autocomplete,
  Button,
  Skeleton,
  SimpleGrid,
  NumberInput,
  Select,
  Switch,
  Divider,
  Grid,
  SegmentedControl,
  Loader,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useQuery } from '@tanstack/react-query';
import { IconSearch, IconCalculator } from '@tabler/icons-react';
import { useDebouncedValue } from '@mantine/hooks';
import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

import { calculateDamage, fetchDamage, searchNations } from '@/api';
import { DamageDashboard } from '@/components/damage';
import { TokenError, LoadingState, ErrorState } from '@/components/common';
import type {
  ApiError,
  DamageCalculationInput,
  DamageResponse,
  DamageWarType,
} from '@/types';

// Per PWPedia "War-Policy" article.
const WAR_POLICY_OPTIONS = [
  {
    value: 'Attrition',
    label: 'Attrition',
    description: 'Infra damage dealt +10%; loot stolen -20%.',
  },
  {
    value: 'Turtle',
    label: 'Turtle',
    description: 'Infra damage taken -10%; loot lost +20%.',
  },
  {
    value: 'Moneybags',
    label: 'Moneybags',
    description: 'Loot stolen -40%; infra damage taken +5%.',
  },
  {
    value: 'Pirate',
    label: 'Pirate',
    description: 'Loot stolen +40%; double chance to lose own improvements in ground/naval attacks.',
  },
  {
    value: 'Tactician',
    label: 'Tactician',
    description: 'Double chance to destroy enemy improvements (ground/naval).',
  },
  {
    value: 'Guardian',
    label: 'Guardian',
    description: 'Improvement loss chance halved; loot stolen +20%.',
  },
  {
    value: 'Covert',
    label: 'Covert',
    description: 'Infra damage taken +5%.',
  },
  {
    value: 'Arcane',
    label: 'Arcane',
    description: 'Infra damage taken +5%.',
  },
  {
    value: 'Blitzkrieg',
    label: 'Blitzkrieg',
    description: 'First 12 turns: infra damage dealt +10% and casualties dealt +10%; if declared on, attacker +1 MAP.',
  },
  {
    value: 'Fortress',
    label: 'Fortress',
    description: 'Starting MAP for both attacker and defender -1.',
  },
];

// Per PWPedia "War-Types" and individual war type articles.
const WAR_TYPE_OPTIONS: { value: DamageWarType; label: string; description: string }[] = [
  {
    value: 'RAID',
    label: 'Raid',
    description: 'War attacker: 25% infra dealt , 100% loot stolen. War defender: 50% infra dealt, 100% loot stolen.',
  },
  {
    value: 'ORDINARY',
    label: 'Ordinary',
    description: 'War attacker & defender: 50% infra dealt, 50% loot stolen.',
  },
  {
    value: 'ATTRITION',
    label: 'Attrition',
    description: 'War attacker: 100% infra dealt, 25% loot stolen. War defender: 100% infra dealt, 50% loot stolen.',
  },
];

const buildNationOptions = (
  nation1Id: number,
  nation2Id: number,
  nation1Label: string,
  nation2Label: string,
  includeNone = false
): { value: string; label: string }[] => {
  const options = [
    ...(includeNone ? [{ value: 'none', label: 'None' }] : []),
    { value: String(nation1Id), label: nation1Label },
    { value: String(nation2Id), label: nation2Label },
  ];

  const seen = new Set<string>();
  return options.filter((option) => {
    if (seen.has(option.value)) {
      return false;
    }
    seen.add(option.value);
    return true;
  });
};

const buildDefaultInputs = (nation1Id: number, nation2Id: number): DamageCalculationInput => ({
  nation1Id,
  nation2Id,
  nation1: {
    id: nation1Id,
    soldiers: 0,
    tanks: 0,
    aircraft: 0,
    ships: 0,
    missiles: 0,
    nukes: 0,
    warpolicy: '',
    vds: false,
    irond: false,
    falloutShelter: false,
    militarySalvage: false,
    advancedPirateEconomy: false,
    soldiersUseMunitions: true,
    cityInfrastructure: 0,
    cityLand: 0,
  },
  nation2: {
    id: nation2Id,
    soldiers: 0,
    tanks: 0,
    aircraft: 0,
    ships: 0,
    missiles: 0,
    nukes: 0,
    warpolicy: '',
    vds: false,
    irond: false,
    falloutShelter: false,
    militarySalvage: false,
    advancedPirateEconomy: false,
    soldiersUseMunitions: true,
    cityInfrastructure: 0,
    cityLand: 0,
  },
  war: {
    attackerId: nation1Id,
    defenderId: nation2Id,
    warType: 'ORDINARY',
    groundControlId: null,
    airSuperiorityId: null,
    navalBlockadeId: null,
    attackerFortified: false,
    defenderFortified: false,
    attackerPeace: false,
    defenderPeace: false,
  },
});

const parseNationIdInput = (value: string): number => {
  if (!value) return 0;
  const match = value.trim().match(/\d{1,10}/);
  return match ? Number(match[0]) : 0;
};

const resolveNationId = async (value: string): Promise<number> => {
  const parsed = parseNationIdInput(value);
  if (parsed) return parsed;
  const query = value.trim();
  if (!query) return 0;
  const results = await searchNations(query, 5);
  return results[0] ? Number(results[0].id) : 0;
};

interface NationAutocompleteFieldProps {
  label: string;
  value: string;
  onCommit: (value: string) => void;
}

const NationAutocompleteField = memo(function NationAutocompleteField({
  label,
  value,
  onCommit,
}: NationAutocompleteFieldProps) {
  const [inputValue, setInputValue] = useState(value);
  const [debouncedInput] = useDebouncedValue(inputValue, 300);

  useEffect(() => {
    setInputValue(value);
  }, [value]);

  const { data: options = [] } = useQuery({
    queryKey: ['nation-search', debouncedInput],
    queryFn: () =>
      debouncedInput.length >= 2 ? searchNations(debouncedInput, 10) : Promise.resolve([]),
    enabled: debouncedInput.length >= 2,
  });

  const optionData = useMemo(
    () =>
      options.slice(0, 6).map((option) => ({
        value: option.label,
        label: option.label,
      })),
    [options]
  );

  return (
    <Autocomplete
      label={label}
      value={inputValue}
      onChange={setInputValue}
      data={optionData}
      limit={6}
      onBlur={() => onCommit(inputValue)}
      onOptionSubmit={(selected) => {
        setInputValue(selected);
        onCommit(selected);
      }}
    />
  );
});

export function DamagePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  const nation1 = params.get('nation1');
  const nation2 = params.get('nation2');
  const [inputNation1, setInputNation1] = useState('');
  const [inputNation2, setInputNation2] = useState('');
  const [nation1Query, setNation1Query] = useState('');
  const [nation2Query, setNation2Query] = useState('');
  const [isCalculating, setIsCalculating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [calculatedData, setCalculatedData] = useState<DamageResponse | null>(null);

  const parsedNation1 = nation1 ? Number(nation1) : 0;
  const parsedNation2 = nation2 ? Number(nation2) : 0;

  const form = useForm<DamageCalculationInput>({
    initialValues: buildDefaultInputs(parsedNation1, parsedNation2),
  });

  const [debouncedInputNation1] = useDebouncedValue(inputNation1, 300);
  const [debouncedInputNation2] = useDebouncedValue(inputNation2, 300);

  const { data: inputNation1Options = [] } = useQuery({
    queryKey: ['nation-search', debouncedInputNation1],
    queryFn: () =>
      debouncedInputNation1.length >= 1 ? searchNations(debouncedInputNation1, 15) : Promise.resolve([]),
    enabled: debouncedInputNation1.length >= 1,
  });

  const { data: inputNation2Options = [] } = useQuery({
    queryKey: ['nation-search', debouncedInputNation2],
    queryFn: () =>
      debouncedInputNation2.length >= 1 ? searchNations(debouncedInputNation2, 15) : Promise.resolve([]),
    enabled: debouncedInputNation2.length >= 1,
  });

  const inputNation1OptionsData = useMemo(
    () =>
      inputNation1Options.slice(0, 6).map((option) => ({
        value: option.label,
        label: option.label,
      })),
    [inputNation1Options]
  );

  const inputNation2OptionsData = useMemo(
    () =>
      inputNation2Options.slice(0, 6).map((option) => ({
        value: option.label,
        label: option.label,
      })),
    [inputNation2Options]
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const nation1Id = await resolveNationId(inputNation1);
    const nation2Id = await resolveNationId(inputNation2);
    if (nation1Id && nation2Id) {
      navigate(`/damage?nation1=${nation1Id}&nation2=${nation2Id}`);
    }
  };

  const {
    data,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['damage', nation1, nation2],
    queryFn: async () => {
      return fetchDamage(parsedNation1, parsedNation2);
    },
    retry: false,
    enabled: !!nation1 && !!nation2,
  });

  useEffect(() => {
    if (data?.inputs) {
      form.setValues(data.inputs);
      setCalculatedData(null);
    }
  }, [data]);

  useEffect(() => {
    setNation1Query(form.values.nation1Id ? String(form.values.nation1Id) : '');
    setNation2Query(form.values.nation2Id ? String(form.values.nation2Id) : '');
  }, [form.values.nation1Id, form.values.nation2Id]);

  const commitNation1Query = useCallback((value: string) => {
    setNation1Query(value);
    form.setFieldValue('nation1Id', parseNationIdInput(value));
  }, [form]);

  const commitNation2Query = useCallback((value: string) => {
    setNation2Query(value);
    form.setFieldValue('nation2Id', parseNationIdInput(value));
  }, [form]);

  const activeData = calculatedData ?? data ?? null;

  const handleCalculate = async () => {
    setFormError(null);
    setIsCalculating(true);
    try {
      const resolvedNation1 = form.values.nation1Id || await resolveNationId(nation1Query);
      const resolvedNation2 = form.values.nation2Id || await resolveNationId(nation2Query);
      if (!resolvedNation1 || !resolvedNation2) {
        setFormError('Please provide valid nation IDs or select from the autocomplete list.');
        setIsCalculating(false);
        return;
      }
      form.setFieldValue('nation1Id', resolvedNation1);
      form.setFieldValue('nation2Id', resolvedNation2);

      const payload: DamageCalculationInput = {
        ...form.values,
        nation1Id: Number(resolvedNation1),
        nation2Id: Number(resolvedNation2),
        nation1: {
          ...form.values.nation1,
          id: Number(resolvedNation1),
        },
        nation2: {
          ...form.values.nation2,
          id: Number(resolvedNation2),
        },
        war: {
          ...form.values.war,
          attackerId: Number(form.values.war.attackerId),
          defenderId: Number(form.values.war.defenderId),
        },
      };

      const response = await calculateDamage(payload);
      setCalculatedData(response);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to calculate damage';
      setFormError(message);
    } finally {
      setIsCalculating(false);
    }
  };

  if (!nation1 || !nation2) {
    return (
      <Container size="xl" py="xl">
        <Stack gap="lg">
          <Title order={1}>Damage Calculator</Title>

          <Paper p="md" withBorder>
            <form onSubmit={handleSubmit}>
              <Stack gap="md">
                <Text size="sm" c="dimmed">
                  Enter two nation IDs to calculate damage potential
                </Text>
                <Group grow>
                  <Autocomplete
                    placeholder="Nation 1 ID, name, or leader"
                    value={inputNation1}
                    onChange={setInputNation1}
                    leftSection={<IconSearch size={16} />}
                    data={inputNation1OptionsData}
                    limit={6}
                    onOptionSubmit={(value) => setInputNation1(value)}
                  />
                  <Autocomplete
                    placeholder="Nation 2 ID, name, or leader"
                    value={inputNation2}
                    onChange={setInputNation2}
                    leftSection={<IconSearch size={16} />}
                    data={inputNation2OptionsData}
                    limit={6}
                    onOptionSubmit={(value) => setInputNation2(value)}
                  />
                  <Button
                    type="submit"
                    size="lg"
                    leftSection={<IconCalculator size={20} />}
                    disabled={!inputNation1.trim() || !inputNation2.trim()}
                  >
                    Calculate Damage
                  </Button>
                </Group>
              </Stack>
            </form>
          </Paper>

          <Stack gap="md">
            <Title order={2}>Damage Analysis</Title>
            <Text c="dimmed">Enter nation IDs above to see damage calculations</Text>

            <Skeleton height={300} radius="md" animate={false} />
            <SimpleGrid cols={2}>
              <Skeleton height={400} radius="md" animate={false} />
              <Skeleton height={400} radius="md" animate={false} />
            </SimpleGrid>
          </Stack>
        </Stack>
      </Container>
    );
  }

  if (isLoading) {
    return <LoadingState message="Loading damage analysis..." />;
  }

  if (error && !activeData) {
    const apiError = error as unknown as ApiError;

    if (apiError.code === 'TOKEN_EXPIRED') {
      return <TokenError type="expired" message={apiError.message} dataType="damage" />;
    }
    if (apiError.code === 'TOKEN_INVALID') {
      return <TokenError type="invalid" message={apiError.message} dataType="damage" />;
    }

    return (
      <ErrorState
        title="Failed to load damage data"
        message={apiError.message || 'An unexpected error occurred'}
        onRetry={() => refetch()}
      />
    );
  }

  if (!activeData) {
    return <ErrorState title="No data" message="No damage data available" />;
  }

  const nation1Label = activeData.nations.nation1.nationName || 'Nation 1';
  const nation2Label = activeData.nations.nation2.nationName || 'Nation 2';
  const attackerName = form.values.war.attackerId === form.values.nation2Id
    ? nation2Label
    : nation1Label;
  const defenderName = attackerName === nation1Label ? nation2Label : nation1Label;
  const warTypeDescription = WAR_TYPE_OPTIONS.find((option) => option.value === form.values.war.warType)?.description;
  const warPolicyDescriptions = Object.fromEntries(
    WAR_POLICY_OPTIONS.map((option) => [option.value, option.description])
  );

  return (
    <Container size="xl" py="md">
      <Stack gap="md">
        <Group justify="space-between" align="flex-start">
          <Stack gap="xs">
            <Title order={2}>Damage Calculator</Title>
            <Text c="dimmed">
              Analyze war damage between two nations. Use this to plan attacks
              and maximize efficiency.
            </Text>
          </Stack>
        </Group>

        <Paper p="lg" withBorder radius="md">
          <form onSubmit={form.onSubmit(handleCalculate)}>
            <Stack gap="lg">
              <div>
                <Title order={3}>Damage Inputs</Title>
                <Text size="sm" c="dimmed">
                  Adjust the assumptions below and re-run the calculator with custom inputs.
                </Text>
              </div>

              <Paper p="md" withBorder radius="md">
                <Stack gap="sm">
                  <Text size="sm" fw={600}>Nation IDs</Text>
                  <Group grow align="flex-end">
                    <NationAutocompleteField
                      label="Nation 1 ID, name, or leader"
                      value={nation1Query}
                      onCommit={commitNation1Query}
                    />
                    <NationAutocompleteField
                      label="Nation 2 ID, name, or leader"
                      value={nation2Query}
                      onCommit={commitNation2Query}
                    />
                    <Button
                      variant="light"
                      type="button"
                      style={{ alignSelf: 'flex-end' }}
                      onClick={async () => {
                        const nation1Id = form.values.nation1Id || await resolveNationId(nation1Query);
                        const nation2Id = form.values.nation2Id || await resolveNationId(nation2Query);
                        if (nation1Id && nation2Id) {
                          navigate(`/damage?nation1=${nation1Id}&nation2=${nation2Id}`);
                        }
                      }}
                    >
                      Reload Nations
                    </Button>
                  </Group>
                </Stack>
              </Paper>

              <Grid gutter="lg">
                <Grid.Col span={{ base: 12, md: 6 }}>
                  <Paper p="md" withBorder radius="md">
                    <Stack gap="sm">
                      <Text size="sm" fw={600}>{nation1Label}</Text>
                      <NumberInput label="Soldiers" {...form.getInputProps('nation1.soldiers')} min={0} />
                      <NumberInput label="Tanks" {...form.getInputProps('nation1.tanks')} min={0} />
                      <NumberInput label="Aircraft" {...form.getInputProps('nation1.aircraft')} min={0} />
                      <NumberInput label="Ships" {...form.getInputProps('nation1.ships')} min={0} />
                      <Select
                        label="War Policy"
                        data={WAR_POLICY_OPTIONS}
                        searchable
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
                        {...form.getInputProps('nation1.warpolicy')}
                      />
                      {form.values.nation1.warpolicy && (
                        <Text size="xs" c="dimmed">
                          {warPolicyDescriptions[form.values.nation1.warpolicy]}
                        </Text>
                      )}
                      <Switch
                        label="Soldiers Use Munitions"
                        description="Apply standard ammo usage for soldier attacks; disable to ignore munition costs."
                        checked={form.values.nation1.soldiersUseMunitions}
                        onChange={(event) => form.setFieldValue('nation1.soldiersUseMunitions', event.currentTarget.checked)}
                      />
                      <Switch
                        label="Vital Defense System"
                        description="Apply VDS modifiers to nuclear strikes (interception + reduced impact)."
                        checked={form.values.nation1.vds}
                        onChange={(event) => form.setFieldValue('nation1.vds', event.currentTarget.checked)}
                      />
                      <Switch
                        label="Iron Dome"
                        description="Apply Iron Dome modifiers to incoming missiles (interception chance)."
                        checked={form.values.nation1.irond}
                        onChange={(event) => form.setFieldValue('nation1.irond', event.currentTarget.checked)}
                      />
                      <Switch
                        label="Fallout Shelter"
                        description="Reduce nuclear strike damage to your city targets in the calc."
                        checked={form.values.nation1.falloutShelter}
                        onChange={(event) => form.setFieldValue('nation1.falloutShelter', event.currentTarget.checked)}
                      />
                      <Switch
                        label="Military Salvage"
                        description="Recover a portion of resources from your unit losses after combat."
                        checked={form.values.nation1.militarySalvage}
                        onChange={(event) => form.setFieldValue('nation1.militarySalvage', event.currentTarget.checked)}
                      />
                      <Switch
                        label="Advanced Pirate Economy"
                        description="Apply pirate-economy bonuses to raid loot and resources."
                        checked={form.values.nation1.advancedPirateEconomy}
                        onChange={(event) => form.setFieldValue('nation1.advancedPirateEconomy', event.currentTarget.checked)}
                      />
                      <Divider my="sm" />
                      <NumberInput label="Target City Infrastructure" {...form.getInputProps('nation1.cityInfrastructure')} min={0} />
                    </Stack>
                  </Paper>
                </Grid.Col>

                <Grid.Col span={{ base: 12, md: 6 }}>
                  <Paper p="md" withBorder radius="md">
                    <Stack gap="sm">
                      <Text size="sm" fw={600}>{nation2Label}</Text>
                      <NumberInput label="Soldiers" {...form.getInputProps('nation2.soldiers')} min={0} />
                      <NumberInput label="Tanks" {...form.getInputProps('nation2.tanks')} min={0} />
                      <NumberInput label="Aircraft" {...form.getInputProps('nation2.aircraft')} min={0} />
                      <NumberInput label="Ships" {...form.getInputProps('nation2.ships')} min={0} />
                      <Select
                        label="War Policy"
                        data={WAR_POLICY_OPTIONS}
                        searchable
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
                        {...form.getInputProps('nation2.warpolicy')}
                      />
                      {form.values.nation2.warpolicy && (
                        <Text size="xs" c="dimmed">
                          {warPolicyDescriptions[form.values.nation2.warpolicy]}
                        </Text>
                      )}
                      <Switch
                        label="Soldiers Use Munitions"
                        description="Apply standard ammo usage for soldier attacks; disable to ignore munition costs."
                        checked={form.values.nation2.soldiersUseMunitions}
                        onChange={(event) => form.setFieldValue('nation2.soldiersUseMunitions', event.currentTarget.checked)}
                      />
                      <Switch
                        label="Vital Defense System"
                        description="Apply VDS modifiers to nuclear strikes (interception + reduced impact)."
                        checked={form.values.nation2.vds}
                        onChange={(event) => form.setFieldValue('nation2.vds', event.currentTarget.checked)}
                      />
                      <Switch
                        label="Iron Dome"
                        description="Apply Iron Dome modifiers to incoming missiles (interception chance)."
                        checked={form.values.nation2.irond}
                        onChange={(event) => form.setFieldValue('nation2.irond', event.currentTarget.checked)}
                      />
                      <Switch
                        label="Fallout Shelter"
                        description="Reduce nuclear strike damage to your city targets in the calc."
                        checked={form.values.nation2.falloutShelter}
                        onChange={(event) => form.setFieldValue('nation2.falloutShelter', event.currentTarget.checked)}
                      />
                      <Switch
                        label="Military Salvage"
                        description="Recover a portion of resources from your unit losses after combat."
                        checked={form.values.nation2.militarySalvage}
                        onChange={(event) => form.setFieldValue('nation2.militarySalvage', event.currentTarget.checked)}
                      />
                      <Switch
                        label="Advanced Pirate Economy"
                        description="Apply pirate-economy bonuses to raid loot and resources."
                        checked={form.values.nation2.advancedPirateEconomy}
                        onChange={(event) => form.setFieldValue('nation2.advancedPirateEconomy', event.currentTarget.checked)}
                      />
                      <Divider my="sm" />
                      <NumberInput label="Target City Infrastructure" {...form.getInputProps('nation2.cityInfrastructure')} min={0} />
                    </Stack>
                  </Paper>
                </Grid.Col>
              </Grid>

              <Paper p="md" withBorder radius="md">
                <Stack gap="sm">
                  <Text size="sm" fw={600}>War State</Text>
                  <Select
                    label="War Type"
                    data={WAR_TYPE_OPTIONS}
                    value={form.values.war.warType}
                    onChange={(value) => form.setFieldValue('war.warType', (value as DamageWarType) || 'ORDINARY')}
                  />
                  {warTypeDescription && (
                    <Text size="xs" c="dimmed">
                      {warTypeDescription}
                    </Text>
                  )}
                  <Text size="sm" fw={600}>Attacker Selection</Text>
                  <Text size="xs" c="dimmed">
                    Choose the war attacker (the nation that declared the war) and the war defender.
                    This affects war type and war policy modifiers. It is separate from which side is
                    making a specific attack in the tables below.
                  </Text>
                  <SegmentedControl
                    fullWidth
                    value={String(form.values.war.attackerId || form.values.nation1Id)}
                    onChange={(value) => {
                      const attackerId = Number(value);
                      const defenderId = attackerId === form.values.nation1Id
                        ? form.values.nation2Id
                        : form.values.nation1Id;
                      form.setFieldValue('war.attackerId', attackerId);
                      form.setFieldValue('war.defenderId', defenderId);
                    }}
                    data={buildNationOptions(
                      form.values.nation1Id,
                      form.values.nation2Id,
                      nation1Label,
                      nation2Label
                    )}
                  />
                  <Divider my="sm" />

                  <Group grow>
                    <Select
                      label="Air Superiority"
                      value={form.values.war.airSuperiorityId ? String(form.values.war.airSuperiorityId) : 'none'}
                      onChange={(value) =>
                        form.setFieldValue('war.airSuperiorityId', value === 'none' ? null : Number(value))
                      }
                      data={buildNationOptions(
                        form.values.nation1Id,
                        form.values.nation2Id,
                        nation1Label,
                        nation2Label,
                        true
                      )}
                    />
                  </Group>

                  <Group grow>
                    <Switch
                      label={`Fortified (${attackerName})`}
                      description="Apply fortified modifier to the attacker."
                      checked={form.values.war.attackerFortified}
                      onChange={(event) => form.setFieldValue('war.attackerFortified', event.currentTarget.checked)}
                    />
                    <Switch
                      label={`Fortified (${defenderName})`}
                      description="Apply fortified modifier to the defender."
                      checked={form.values.war.defenderFortified}
                      onChange={(event) => form.setFieldValue('war.defenderFortified', event.currentTarget.checked)}
                    />
                  </Group>
                </Stack>
              </Paper>

              {formError && (
                <Text c="red" size="sm">
                  {formError}
                </Text>
              )}

              <Group justify="center">
                <Button
                  type="submit"
                  size="lg"
                  leftSection={isCalculating ? <Loader size="xs" /> : <IconCalculator size={20} />}
                  loading={isCalculating}
                  fullWidth
                >
                  Recalculate Damage
                </Button>
              </Group>
            </Stack>
          </form>
        </Paper>

        <DamageDashboard data={activeData} />
      </Stack>
    </Container>
  );
}
