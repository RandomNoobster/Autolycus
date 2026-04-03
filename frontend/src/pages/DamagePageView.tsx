/**
 * Damage Page
 *
 * Displays damage calculator with charts and tables (public page, no authentication required).
 */

import {
  Alert,
  Box,
  Card,
  Container,
  Title,
  Text,
  Stack,
  Group,
  Flex,
  Paper,
  Autocomplete,
  Button,
  SimpleGrid,
  NumberInput,
  Select,
  Switch,
  Divider,
  Grid,
  SegmentedControl,
  Loader,
  Image,
  List,
  Progress,
  ThemeIcon,
  useMantineColorScheme,
  useMantineTheme,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useQuery } from "@tanstack/react-query";
import {
  IconBrandDiscord,
  IconCalculator,
  IconSearch,
  IconSword,
  IconTarget,
} from "@tabler/icons-react";
import { useDebouncedValue } from "@mantine/hooks";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";

import {
  calculateDamage,
  fetchDamage,
  fetchLinkedActiveWars,
  searchNations,
} from "@/api";
import { getDiscordLoginUrl, getLinkedNation } from "@/api/auth";
import { toApiError } from "@/api/errors";
import { DamageDashboard, DamagePageSkeleton } from "@/components/damage";
import { ErrorState } from "@/components/common";
import type {
  ApiError,
  DamageCalculationInput,
  DamageLinkedActiveWarsResponse,
  DamageLinkedWarPreset,
  DamageResponse,
  DamageWarType,
} from "@/types";

// Per PWPedia "War-Policy" article.
const WAR_POLICY_OPTIONS = [
  {
    value: "Attrition",
    label: "Attrition",
    description: "Infra damage dealt +10%; loot stolen -20%.",
  },
  {
    value: "Turtle",
    label: "Turtle",
    description: "Infra damage taken -10%; loot lost +20%.",
  },
  {
    value: "Moneybags",
    label: "Moneybags",
    description: "Loot stolen -40%; infra damage taken +5%.",
  },
  {
    value: "Pirate",
    label: "Pirate",
    description:
      "Loot stolen +40%; double chance to lose own improvements in ground/naval attacks.",
  },
  {
    value: "Tactician",
    label: "Tactician",
    description: "Double chance to destroy enemy improvements (ground/naval).",
  },
  {
    value: "Guardian",
    label: "Guardian",
    description: "Improvement loss chance halved; loot stolen +20%.",
  },
  {
    value: "Covert",
    label: "Covert",
    description: "Infra damage taken +5%.",
  },
  {
    value: "Arcane",
    label: "Arcane",
    description: "Infra damage taken +5%.",
  },
  {
    value: "Blitzkrieg",
    label: "Blitzkrieg",
    description:
      "First 12 turns: infra damage dealt +10% and casualties dealt +10%; if declared on, attacker +1 MAP.",
  },
  {
    value: "Fortress",
    label: "Fortress",
    description: "Starting MAP for both attacker and defender -1.",
  },
];

// Per PWPedia "War-Types" and individual war type articles.
const WAR_TYPE_OPTIONS: {
  value: DamageWarType;
  label: string;
  description: string;
}[] = [
  {
    value: "RAID",
    label: "Raid",
    description:
      "War attacker: 25% infra dealt , 100% loot stolen. War defender: 50% infra dealt, 100% loot stolen.",
  },
  {
    value: "ORDINARY",
    label: "Ordinary",
    description: "War attacker & defender: 50% infra dealt, 50% loot stolen.",
  },
  {
    value: "ATTRITION",
    label: "Attrition",
    description:
      "War attacker: 100% infra dealt, 25% loot stolen. War defender: 100% infra dealt, 50% loot stolen.",
  },
];

type UnitKey = "soldiers" | "tanks" | "aircraft" | "ships";

interface UnitConfig {
  label: string;
  perDay: number;
  capacity: number;
  improvementLabel: string;
  improvementKey: keyof MmrCounts;
}

interface MmrCounts {
  barracks: number;
  factories: number;
  hangars: number;
  drydocks: number;
}

// Per PWPedia: "Soldiers", "Tanks", "Planes", and "Ships" articles.
const UNIT_CONFIG: Record<UnitKey, UnitConfig> = {
  soldiers: {
    label: "Soldiers",
    perDay: 1000,
    capacity: 3000,
    improvementLabel: "Barracks",
    improvementKey: "barracks",
  },
  tanks: {
    label: "Tanks",
    perDay: 50,
    capacity: 250,
    improvementLabel: "Factories",
    improvementKey: "factories",
  },
  aircraft: {
    label: "Aircraft",
    perDay: 3,
    capacity: 15,
    improvementLabel: "Hangars",
    improvementKey: "hangars",
  },
  ships: {
    label: "Ships",
    perDay: 1,
    capacity: 5,
    improvementLabel: "Drydocks",
    improvementKey: "drydocks",
  },
};

const MAX_MMR_COUNTS: MmrCounts = {
  barracks: 5,
  factories: 5,
  hangars: 5,
  drydocks: 3,
};

const normalizeNumberInput = (value: string | number | null): number => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

const clampNumber = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), max);

interface UnitInputWithRebuyProps {
  label: string;
  value: number;
  max: number;
  dailyRebuy: number;
  onChange: (value: number) => void;
  onReset?: () => void;
  isDirty?: boolean;
}

interface ResetLinkProps {
  isDirty: boolean;
  onClick?: () => void;
}

const ResetLink = memo(function ResetLink({
  isDirty,
  onClick,
}: ResetLinkProps) {
  return (
    <Text
      size="xs"
      c={isDirty ? "orange" : "dimmed"}
      fw={600}
      style={{ cursor: isDirty ? "pointer" : "default" }}
      onClick={isDirty ? onClick : undefined}
    >
      Reset to current
    </Text>
  );
});

const UnitInputWithRebuy = memo(function UnitInputWithRebuy({
  label,
  value,
  max,
  dailyRebuy,
  onChange,
  onReset,
  isDirty,
}: UnitInputWithRebuyProps) {
  const addUnits = (days: number) => {
    const increment = dailyRebuy * days;
    if (increment <= 0) return;
    onChange(clampNumber(value + increment, 0, max));
  };

  const removeUnits = (days: number) => {
    const decrement = dailyRebuy * days;
    if (decrement <= 0) return;
    onChange(clampNumber(value - decrement, 0, max));
  };

  return (
    <Stack gap={4}>
      <Group align="flex-end" justify="space-between" wrap="wrap">
        <NumberInput
          label={label}
          value={value}
          onChange={(nextValue) =>
            onChange(clampNumber(normalizeNumberInput(nextValue), 0, max))
          }
          min={0}
          max={max}
          allowDecimal={false}
          step={1}
          style={{ flex: 1, minWidth: 160 }}
        />
        <Group gap="xs">
          <Button
            size="xs"
            variant="light"
            onClick={() => removeUnits(1)}
            disabled={dailyRebuy <= 0 || value <= 0}
          >
            -1 day
          </Button>
          <Button
            size="xs"
            variant="light"
            onClick={() => addUnits(1)}
            disabled={dailyRebuy <= 0 || value >= max}
          >
            +1 day
          </Button>
          <Button
            size="xs"
            variant="light"
            onClick={() => addUnits(2)}
            disabled={dailyRebuy <= 0 || value >= max}
          >
            +2 days
          </Button>
        </Group>
      </Group>
      <Text size="xs" c="dimmed">
        Daily buy: {dailyRebuy.toLocaleString()} · Double buy:{" "}
        {(dailyRebuy * 2).toLocaleString()} · Max: {max.toLocaleString()}
      </Text>
      {onReset && <ResetLink isDirty={Boolean(isDirty)} onClick={onReset} />}
    </Stack>
  );
});

interface NationUnitPlannerProps {
  form: DamageForm;
  basePath: "nation1" | "nation2";
  initialCityCount?: number;
  baselineUnits?: {
    soldiers: number;
    tanks: number;
    aircraft: number;
    ships: number;
  };
}

// Per PWPedia: "Propaganda-Bureau" and "Beige-Buff" articles.
const NationUnitPlanner = memo(function NationUnitPlanner({
  form,
  basePath,
  initialCityCount,
  baselineUnits,
}: NationUnitPlannerProps) {
  const [cityCount, setCityCount] = useState(0);
  const [mmrCounts, setMmrCounts] = useState<MmrCounts>({
    barracks: 5,
    factories: 5,
    hangars: 5,
    drydocks: 3,
  });
  const [propagandaBureau, setPropagandaBureau] = useState(false);
  const baselineRef = useRef({
    units: {
      soldiers: form.values[basePath].soldiers,
      tanks: form.values[basePath].tanks,
      aircraft: form.values[basePath].aircraft,
      ships: form.values[basePath].ships,
    },
    cityCount: initialCityCount ?? 0,
    mmrCounts: {
      barracks: 5,
      factories: 5,
      hangars: 5,
      drydocks: 3,
    },
  });
  const lastNationIdRef = useRef<number | null>(null);

  useEffect(() => {
    const nationId = form.values[basePath].id;
    if (!nationId || nationId === lastNationIdRef.current) return;
    lastNationIdRef.current = nationId;
    const initialCities = initialCityCount ?? 0;
    const defaultMmr = {
      barracks: 5,
      factories: 5,
      hangars: 5,
      drydocks: 3,
    };
    setCityCount(initialCities);
    setMmrCounts(defaultMmr);
    baselineRef.current = {
      units: {
        soldiers: form.values[basePath].soldiers,
        tanks: form.values[basePath].tanks,
        aircraft: form.values[basePath].aircraft,
        ships: form.values[basePath].ships,
      },
      cityCount: initialCities,
      mmrCounts: defaultMmr,
    };
  }, [basePath, form.values, form.values[basePath].id, initialCityCount]);

  useEffect(() => {
    if (!baselineUnits) return;
    baselineRef.current.units = {
      soldiers: baselineUnits.soldiers,
      tanks: baselineUnits.tanks,
      aircraft: baselineUnits.aircraft,
      ships: baselineUnits.ships,
    };
    if (typeof initialCityCount === "number") {
      baselineRef.current.cityCount = initialCityCount;
    }
  }, [baselineUnits, initialCityCount]);

  const totalImprovements = useMemo(
    () => ({
      barracks: mmrCounts.barracks * cityCount,
      factories: mmrCounts.factories * cityCount,
      hangars: mmrCounts.hangars * cityCount,
      drydocks: mmrCounts.drydocks * cityCount,
    }),
    [mmrCounts, cityCount],
  );

  const dailyMultiplier = 1 + (propagandaBureau ? 0.1 : 0);

  const maxUnits = useMemo(
    () => ({
      soldiers: totalImprovements.barracks * UNIT_CONFIG.soldiers.capacity,
      tanks: totalImprovements.factories * UNIT_CONFIG.tanks.capacity,
      aircraft: totalImprovements.hangars * UNIT_CONFIG.aircraft.capacity,
      ships: totalImprovements.drydocks * UNIT_CONFIG.ships.capacity,
    }),
    [totalImprovements],
  );

  const dailyRebuy = useMemo(
    () => ({
      soldiers: Math.floor(
        totalImprovements.barracks *
          UNIT_CONFIG.soldiers.perDay *
          dailyMultiplier,
      ),
      tanks: Math.floor(
        totalImprovements.factories *
          UNIT_CONFIG.tanks.perDay *
          dailyMultiplier,
      ),
      aircraft: Math.floor(
        totalImprovements.hangars *
          UNIT_CONFIG.aircraft.perDay *
          dailyMultiplier,
      ),
      ships: Math.floor(
        totalImprovements.drydocks * UNIT_CONFIG.ships.perDay * dailyMultiplier,
      ),
    }),
    [totalImprovements, dailyMultiplier],
  );

  useEffect(() => {
    (["soldiers", "tanks", "aircraft", "ships"] as UnitKey[]).forEach(
      (unit) => {
        const current = form.values[basePath][unit];
        const max = maxUnits[unit];
        if (current > max) {
          form.setFieldValue(`${basePath}.${unit}`, max);
        }
      },
    );
  }, [basePath, form, maxUnits]);

  const updateMmrCount = (key: keyof MmrCounts, value: number) => {
    setMmrCounts((prev) => ({
      ...prev,
      [key]: clampNumber(value, 0, MAX_MMR_COUNTS[key]),
    }));
  };

  const setUnitValue = (unit: UnitKey, value: number) => {
    form.setFieldValue(
      `${basePath}.${unit}`,
      clampNumber(value, 0, maxUnits[unit]),
    );
  };

  return (
    <Stack gap="sm">
      <Text size="sm" fw={600}>
        Unit Planner
      </Text>
      <Group grow align="flex-end">
        <Stack gap={4}>
          <NumberInput
            label="Cities"
            value={cityCount}
            onChange={(value) =>
              setCityCount(Math.max(0, normalizeNumberInput(value)))
            }
            min={0}
            allowDecimal={false}
          />
          <ResetLink
            isDirty={cityCount !== baselineRef.current.cityCount}
            onClick={() => setCityCount(baselineRef.current.cityCount)}
          />
        </Stack>
        <Switch
          label="Propaganda Bureau"
          description="+10% daily recruits for soldiers, tanks, aircraft, and ships."
          checked={propagandaBureau}
          onChange={(event) => setPropagandaBureau(event.currentTarget.checked)}
        />
      </Group>
      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs">
        <Stack gap={4}>
          <NumberInput
            label="Barracks per City"
            value={mmrCounts.barracks}
            onChange={(value) =>
              updateMmrCount("barracks", normalizeNumberInput(value))
            }
            min={0}
            max={MAX_MMR_COUNTS.barracks}
            allowDecimal={false}
          />
          <ResetLink
            isDirty={
              mmrCounts.barracks !== baselineRef.current.mmrCounts.barracks
            }
            onClick={() =>
              updateMmrCount("barracks", baselineRef.current.mmrCounts.barracks)
            }
          />
        </Stack>
        <Stack gap={4}>
          <NumberInput
            label="Factories per City"
            value={mmrCounts.factories}
            onChange={(value) =>
              updateMmrCount("factories", normalizeNumberInput(value))
            }
            min={0}
            max={MAX_MMR_COUNTS.factories}
            allowDecimal={false}
          />
          <ResetLink
            isDirty={
              mmrCounts.factories !== baselineRef.current.mmrCounts.factories
            }
            onClick={() =>
              updateMmrCount(
                "factories",
                baselineRef.current.mmrCounts.factories,
              )
            }
          />
        </Stack>
        <Stack gap={4}>
          <NumberInput
            label="Hangars per City"
            value={mmrCounts.hangars}
            onChange={(value) =>
              updateMmrCount("hangars", normalizeNumberInput(value))
            }
            min={0}
            max={MAX_MMR_COUNTS.hangars}
            allowDecimal={false}
          />
          <ResetLink
            isDirty={
              mmrCounts.hangars !== baselineRef.current.mmrCounts.hangars
            }
            onClick={() =>
              updateMmrCount("hangars", baselineRef.current.mmrCounts.hangars)
            }
          />
        </Stack>
        <Stack gap={4}>
          <NumberInput
            label="Drydocks per City"
            value={mmrCounts.drydocks}
            onChange={(value) =>
              updateMmrCount("drydocks", normalizeNumberInput(value))
            }
            min={0}
            max={MAX_MMR_COUNTS.drydocks}
            allowDecimal={false}
          />
          <ResetLink
            isDirty={
              mmrCounts.drydocks !== baselineRef.current.mmrCounts.drydocks
            }
            onClick={() =>
              updateMmrCount("drydocks", baselineRef.current.mmrCounts.drydocks)
            }
          />
        </Stack>
      </SimpleGrid>
      <Divider my="xs" />
      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
        <UnitInputWithRebuy
          label={UNIT_CONFIG.soldiers.label}
          value={form.values[basePath].soldiers}
          max={maxUnits.soldiers}
          dailyRebuy={dailyRebuy.soldiers}
          onChange={(value) => setUnitValue("soldiers", value)}
          onReset={() =>
            setUnitValue("soldiers", baselineRef.current.units.soldiers)
          }
          isDirty={
            form.values[basePath].soldiers !==
            baselineRef.current.units.soldiers
          }
        />
        <UnitInputWithRebuy
          label={UNIT_CONFIG.tanks.label}
          value={form.values[basePath].tanks}
          max={maxUnits.tanks}
          dailyRebuy={dailyRebuy.tanks}
          onChange={(value) => setUnitValue("tanks", value)}
          onReset={() => setUnitValue("tanks", baselineRef.current.units.tanks)}
          isDirty={
            form.values[basePath].tanks !== baselineRef.current.units.tanks
          }
        />
        <UnitInputWithRebuy
          label={UNIT_CONFIG.aircraft.label}
          value={form.values[basePath].aircraft}
          max={maxUnits.aircraft}
          dailyRebuy={dailyRebuy.aircraft}
          onChange={(value) => setUnitValue("aircraft", value)}
          onReset={() =>
            setUnitValue("aircraft", baselineRef.current.units.aircraft)
          }
          isDirty={
            form.values[basePath].aircraft !==
            baselineRef.current.units.aircraft
          }
        />
        <UnitInputWithRebuy
          label={UNIT_CONFIG.ships.label}
          value={form.values[basePath].ships}
          max={maxUnits.ships}
          dailyRebuy={dailyRebuy.ships}
          onChange={(value) => setUnitValue("ships", value)}
          onReset={() => setUnitValue("ships", baselineRef.current.units.ships)}
          isDirty={
            form.values[basePath].ships !== baselineRef.current.units.ships
          }
        />
      </SimpleGrid>
      <Text size="xs" c="dimmed">
        Max units = MMR improvements per city × cities. Limits here do not
        account for population caps or military research.
      </Text>
    </Stack>
  );
});

const buildNationOptions = (
  nation1Id: number,
  nation2Id: number,
  nation1Label: string,
  nation2Label: string,
  includeNone = false,
): { value: string; label: string }[] => {
  const options = [
    ...(includeNone ? [{ value: "none", label: "None" }] : []),
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

const buildDefaultInputs = (
  nation1Id: number,
  nation2Id: number,
): DamageCalculationInput => ({
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
    warpolicy: "",
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
    warpolicy: "",
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
    warType: "ORDINARY",
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
    queryKey: ["nation-search", debouncedInput],
    queryFn: () =>
      debouncedInput.length >= 2
        ? searchNations(debouncedInput, 10)
        : Promise.resolve([]),
    enabled: debouncedInput.length >= 2,
  });

  const optionData = useMemo(
    () =>
      options.slice(0, 6).map((option) => ({
        value: option.label,
        label: option.label,
      })),
    [options],
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

type DamageForm = ReturnType<typeof useForm<DamageCalculationInput>>;

interface DamageNationSearchRowProps {
  form: DamageForm;
  nation1Query: string;
  nation2Query: string;
  onCommitNation1: (value: string) => void;
  onCommitNation2: (value: string) => void;
}

function DamageNationSearchRow({
  form,
  nation1Query,
  nation2Query,
  onCommitNation1,
  onCommitNation2,
}: DamageNationSearchRowProps) {
  const navigate = useNavigate();

  return (
    <Paper p="md" withBorder radius="md">
      <Stack gap="sm">
        <Flex
          direction={{ base: "column", sm: "row" }}
          gap="sm"
          align={{ base: "stretch", sm: "flex-end" }}
          wrap="nowrap"
        >
          <Box flex={{ sm: 1 }} miw={{ sm: 0 }}>
            <NationAutocompleteField
              label="Nation 1 ID, name, or leader"
              value={nation1Query}
              onCommit={onCommitNation1}
            />
          </Box>
          <Box flex={{ sm: 1 }} miw={{ sm: 0 }}>
            <NationAutocompleteField
              label="Nation 2 ID, name, or leader"
              value={nation2Query}
              onCommit={onCommitNation2}
            />
          </Box>
          <Button
            variant="light"
            type="button"
            onClick={async () => {
              const nation1Id =
                form.values.nation1Id ||
                (await resolveNationId(nation1Query));
              const nation2Id =
                form.values.nation2Id ||
                (await resolveNationId(nation2Query));
              if (nation1Id && nation2Id) {
                navigate(`/damage?nation1=${nation1Id}&nation2=${nation2Id}`);
              }
            }}
          >
            Reload Nations
          </Button>
        </Flex>
      </Stack>
    </Paper>
  );
}

function DamageCalculatorPageHeader() {
  return (
    <Group justify="space-between" align="flex-start">
      <Stack gap="xs">
        <Title order={2}>Damage Calculator</Title>
        <Text c="dimmed">
          Analyze war damage between two nations. Use this to plan attacks and
          maximize efficiency.
        </Text>
      </Stack>
    </Group>
  );
}

interface NationDamageModifiersProps {
  form: DamageForm;
  basePath: "nation1" | "nation2";
}

// Per PWPedia: "Soldiers", "Vital-Defense-System", "Iron-Dome",
// "Fallout-Shelter", "Military-Salvage", and "Advanced-Pirate-Economy" articles.
const NationDamageModifiers = memo(function NationDamageModifiers({
  form,
  basePath,
}: NationDamageModifiersProps) {
  const isChecked = (
    field:
      | "soldiersUseMunitions"
      | "vds"
      | "irond"
      | "falloutShelter"
      | "militarySalvage"
      | "advancedPirateEconomy",
  ) => Boolean(form.values[basePath][field]);

  const handleToggle = (
    field:
      | "soldiersUseMunitions"
      | "vds"
      | "irond"
      | "falloutShelter"
      | "militarySalvage"
      | "advancedPirateEconomy",
    checked: boolean,
  ) => {
    form.setFieldValue(`${basePath}.${field}`, checked);
  };

  return (
    <>
      <Switch
        label="Soldiers Use Munitions"
        description="Soldiers fight at 175% combat value with munitions (1 munition per 5,000 soldiers per ground battle)."
        checked={isChecked("soldiersUseMunitions")}
        onChange={(event) =>
          handleToggle("soldiersUseMunitions", event.currentTarget.checked)
        }
      />
      <Switch
        label="Vital Defense System"
        description="25% chance to shoot down incoming nukes; reduces non-power-plant, non-military improvements destroyed by a nuke by 1."
        checked={isChecked("vds")}
        onChange={(event) => handleToggle("vds", event.currentTarget.checked)}
      />
      <Switch
        label="Iron Dome"
        description="30% chance to shoot down incoming missiles; reduces improvements destroyed by a missile by 1."
        checked={isChecked("irond")}
        onChange={(event) => handleToggle("irond", event.currentTarget.checked)}
      />
      <Switch
        label="Fallout Shelter"
        description="Nukes: infrastructure damage -10%, fallout length -25%."
        checked={isChecked("falloutShelter")}
        onChange={(event) =>
          handleToggle("falloutShelter", event.currentTarget.checked)
        }
      />
      <Switch
        label="Military Salvage"
        description="Recover 5% of steel and aluminum costs from units lost in victorious war attacks (based on both sides' losses)."
        checked={isChecked("militarySalvage")}
        onChange={(event) =>
          handleToggle("militarySalvage", event.currentTarget.checked)
        }
      />
      <Switch
        label="Advanced Pirate Economy"
        description="+5% loot from ground attacks and +10% loot from a defeated nation and its alliance bank."
        checked={isChecked("advancedPirateEconomy")}
        onChange={(event) =>
          handleToggle("advancedPirateEconomy", event.currentTarget.checked)
        }
      />
      <Divider my="sm" />
      <NumberInput
        label="Target City Infrastructure"
        {...form.getInputProps(`${basePath}.cityInfrastructure`)}
        min={0}
      />
    </>
  );
});

function PresetFlagImage({
  src,
  alt,
  w,
  h,
}: {
  src: string | null | undefined;
  alt: string;
  w: number;
  h: number;
}) {
  const [visible, setVisible] = useState(!!src);
  if (!src || !visible) return null;
  return (
    <Image
      src={src}
      alt={alt}
      w={w}
      h={h}
      radius="sm"
      fit="contain"
      style={{ flexShrink: 0 }}
      onError={() => setVisible(false)}
    />
  );
}

function DamageDiscordPerkPromo() {
  const { colorScheme } = useMantineColorScheme();
  const isLight = colorScheme === "light";
  const loginUrl = getDiscordLoginUrl("/damage");

  return (
    <Card
      padding={0}
      radius="md"
      withBorder
      style={{
        overflow: "hidden",
        borderColor: isLight
          ? "var(--mantine-color-indigo-2)"
          : "var(--mantine-color-dark-4)",
        background: isLight
          ? "linear-gradient(145deg, rgba(99, 102, 241, 0.06) 0%, rgba(249, 115, 22, 0.08) 50%, rgba(255, 255, 255, 0.95) 100%)"
          : "linear-gradient(145deg, rgba(88, 101, 242, 0.12) 0%, rgba(249, 115, 22, 0.1) 45%, var(--mantine-color-dark-7) 100%)",
        boxShadow: isLight
          ? "0 12px 40px rgba(15, 23, 42, 0.06)"
          : "0 16px 48px rgba(0, 0, 0, 0.35)",
      }}
    >
      <Stack gap={0}>
        <Box
          px="lg"
          pt="md"
          pb="sm"
          style={{
            borderBottom: `1px solid ${isLight ? "var(--mantine-color-gray-2)" : "var(--mantine-color-dark-5)"}`,
          }}
        >
          <Group gap="sm" wrap="nowrap" align="flex-start">
            <ThemeIcon
              size={44}
              radius="md"
              variant="gradient"
              gradient={{ from: "indigo", to: "orange", deg: 125 }}
            >
              <IconCalculator size={22} stroke={1.5} />
            </ThemeIcon>
            <Stack gap="xs" style={{ flex: 1, minWidth: 0 }}>
              <div>
                <Text size="xs" tt="uppercase" fw={700} c="dimmed" lts={1.2}>
                  Discord perk
                </Text>
                <Title order={3} style={{ lineHeight: 1.25 }}>
                  Your live active wars
                </Title>
              </div>
              <Text size="sm" c="dimmed">
                Link your P&amp;W nation through Discord to open the damage
                calculator on any active war in one click — with nation and
                alliance flags.
              </Text>
            </Stack>
          </Group>
        </Box>

        <Stack px="lg" py="md" gap="sm">
          <List spacing="xs" size="sm" center>
            <List.Item
              icon={
                <ThemeIcon color="indigo" variant="light" size={26} radius="md">
                  <IconSword size={14} />
                </ThemeIcon>
              }
            >
              Presets for every war you are in right now
            </List.Item>
            <List.Item
              icon={
                <ThemeIcon color="indigo" variant="light" size={26} radius="md">
                  <IconTarget size={14} />
                </ThemeIcon>
              }
            >
              Uses the same live data as the rest of the calculator
            </List.Item>
          </List>

          <Button
            component="a"
            href={loginUrl}
            size="sm"
            fullWidth
            color="indigo"
            variant="filled"
            leftSection={<IconBrandDiscord size={18} />}
          >
            Continue with Discord
          </Button>
          <Text size="xs" c="dimmed">
            We use Discord to attach your nation to your browser session.
          </Text>
        </Stack>
      </Stack>
    </Card>
  );
}

/** Same tints as DamageTable attacker (blue) / defender (red) columns. */
const DAMAGE_PRESET_ATTACKER_BG = "rgba(34, 139, 230, 0.12)";
const DAMAGE_PRESET_DEFENDER_BG = "rgba(250, 82, 82, 0.12)";
const DAMAGE_PRESET_ATTACKER_ACCENT = "rgb(34, 139, 230)";
const DAMAGE_PRESET_DEFENDER_ACCENT = "rgb(250, 82, 82)";

interface DamageWarPresetsSectionProps {
  wars: DamageLinkedWarPreset[];
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  onRetry: () => void;
  onSelectWar: (w: DamageLinkedWarPreset) => void;
  /** Current URL pair: Nation 1 = your nation, Nation 2 = opponent (highlights matching preset). */
  selectedNation1Id?: number | null;
  selectedNation2Id?: number | null;
}

function DamageWarPresetsSection({
  wars,
  isLoading,
  isError,
  error,
  onRetry,
  onSelectWar,
  selectedNation1Id = null,
  selectedNation2Id = null,
}: DamageWarPresetsSectionProps) {
  const { colorScheme } = useMantineColorScheme();
  const theme = useMantineTheme();
  const isDark = colorScheme === "dark";

  if (isLoading) {
    return (
      <Stack gap="xs">
        <Text size="sm" fw={600}>
          Your active wars
        </Text>
        <Group gap="xs">
          <Loader size="sm" />
          <Text size="sm" c="dimmed">
            Loading your wars…
          </Text>
        </Group>
      </Stack>
    );
  }

  if (isError) {
    const ae = toApiError(error);
    return (
      <Alert color="red" title="Couldn’t load active wars" variant="light">
        <Text size="sm">{ae.message}</Text>
        <Button variant="light" size="xs" mt="sm" onClick={() => onRetry()}>
          Try again
        </Button>
      </Alert>
    );
  }

  const canHighlightSelection =
    selectedNation1Id != null &&
    selectedNation2Id != null &&
    !Number.isNaN(selectedNation1Id) &&
    !Number.isNaN(selectedNation2Id);

  return (
    <Stack gap="sm">
      <Text size="sm" fw={600}>
        Your active wars
      </Text>
      {wars.length === 0 ? (
        <Text size="sm" c="dimmed">
          No active wars right now.
        </Text>
      ) : (
        <Group gap="sm" align="stretch" wrap="wrap">
          {wars.map((w) => {
            const offensive = w.linked_stance === "offensive";
            const accent = isDark
              ? offensive
                ? theme.colors.blue[4]
                : theme.colors.red[5]
              : offensive
                ? DAMAGE_PRESET_ATTACKER_ACCENT
                : DAMAGE_PRESET_DEFENDER_ACCENT;
            const bg = isDark
              ? offensive
                ? "rgba(96, 167, 255, 0.14)"
                : "rgba(255, 130, 130, 0.12)"
              : offensive
                ? DAMAGE_PRESET_ATTACKER_BG
                : DAMAGE_PRESET_DEFENDER_BG;
            const statusColor = isDark
              ? offensive
                ? ("blue.3" as const)
                : ("red.4" as const)
              : offensive
                ? ("blue.6" as const)
                : ("red.6" as const);
            const subtleText = isDark ? ("gray.5" as const) : ("dimmed" as const);
            const allianceText = isDark ? ("gray.4" as const) : ("dimmed" as const);
            const res = Math.min(100, Math.max(0, w.linked_resistance));
            const maps = Math.min(12, Math.max(0, w.linked_maps));
            const isSelected =
              canHighlightSelection &&
              w.opponent_id === selectedNation2Id &&
              (w.attacker_id === selectedNation1Id ||
                w.defender_id === selectedNation1Id);

            const progressStyles = isDark
              ? {
                  root: { backgroundColor: theme.colors.dark[5] },
                  section: {
                    backgroundColor: offensive
                      ? theme.colors.blue[4]
                      : theme.colors.red[5],
                  },
                }
              : undefined;

            const cardShadow = isSelected
              ? isDark
                ? `0 0 0 2px ${accent}, 0 0 0 6px rgba(0, 0, 0, 0.55)`
                : `0 0 0 2px ${accent}, 0 0 0 4px var(--mantine-color-body)`
              : isDark
                ? "0 2px 8px rgba(0, 0, 0, 0.35)"
                : undefined;

            return (
              <Paper
                key={`${w.attacker_id}-${w.defender_id}`}
                component="button"
                type="button"
                withBorder={!isDark}
                radius="md"
                p="sm"
                onClick={() => onSelectWar(w)}
                aria-label={`Open damage calculator versus ${w.opponent_name}`}
                aria-pressed={isSelected}
                style={{
                  cursor: "pointer",
                  textAlign: "left",
                  width: "100%",
                  maxWidth: 280,
                  backgroundColor: bg,
                  border: isDark
                    ? `1px solid ${theme.colors.dark[4]}`
                    : undefined,
                  borderLeft: `4px solid ${accent}`,
                  boxShadow: cardShadow,
                  transition: "box-shadow 120ms ease",
                }}
              >
                <Stack gap={6} align="stretch">
                  <Group gap="sm" wrap="nowrap" align="flex-start">
                    <PresetFlagImage
                      src={w.opponent_flag_url}
                      alt=""
                      w={28}
                      h={20}
                    />
                    <Stack gap={2} align="flex-start" style={{ minWidth: 0, flex: 1 }}>
                      <Text
                        size="10px"
                        fw={700}
                        tt="uppercase"
                        c={statusColor}
                        lts={0.6}
                      >
                        {offensive ? "Attacking" : "Defending"}
                      </Text>
                      <Text
                        size="sm"
                        fw={600}
                        lineClamp={1}
                        style={
                          isDark ? { color: theme.white } : undefined
                        }
                      >
                        vs {w.opponent_name}
                      </Text>
                      {w.opponent_alliance_name ? (
                        <Group gap={6} wrap="nowrap" style={{ minWidth: 0 }}>
                          <PresetFlagImage
                            src={w.opponent_alliance_flag_url}
                            alt=""
                            w={18}
                            h={18}
                          />
                          <Text size="xs" c={allianceText} lineClamp={1}>
                            {w.opponent_alliance_name}
                          </Text>
                        </Group>
                      ) : null}
                    </Stack>
                  </Group>
                  <Stack gap={4}>
                    <Group justify="space-between" gap="xs" wrap="nowrap">
                      <Text size="10px" c={subtleText} tt="uppercase" fw={600}>
                        Resistance
                      </Text>
                      <Text size="10px" c={subtleText} ff="monospace" fw={500}>
                        {res}/100
                      </Text>
                    </Group>
                    <Progress
                      value={res}
                      size="xs"
                      color={offensive ? "blue" : "red"}
                      styles={progressStyles}
                    />
                    <Group justify="space-between" gap="xs" wrap="nowrap">
                      <Text size="10px" c={subtleText} tt="uppercase" fw={600}>
                        MAPs
                      </Text>
                      <Text size="10px" c={subtleText} ff="monospace" fw={500}>
                        {maps}/12
                      </Text>
                    </Group>
                    <Progress
                      value={(maps / 12) * 100}
                      size="xs"
                      color={offensive ? "blue" : "red"}
                      styles={progressStyles}
                    />
                  </Stack>
                </Stack>
              </Paper>
            );
          })}
        </Group>
      )}
    </Stack>
  );
}

export function DamagePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  const nation1 = params.get("nation1");
  const nation2 = params.get("nation2");
  const [inputNation1, setInputNation1] = useState("");
  const [inputNation2, setInputNation2] = useState("");
  const [nation1Query, setNation1Query] = useState("");
  const [nation2Query, setNation2Query] = useState("");
  const [hasTouchedNation1Input, setHasTouchedNation1Input] = useState(false);
  const [isCalculating, setIsCalculating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [calculatedData, setCalculatedData] = useState<DamageResponse | null>(
    null,
  );

  const parsedNation1 = nation1 ? Number(nation1) : 0;
  const parsedNation2 = nation2 ? Number(nation2) : 0;

  const form = useForm<DamageCalculationInput>({
    initialValues: buildDefaultInputs(parsedNation1, parsedNation2),
  });

  const [debouncedInputNation1] = useDebouncedValue(inputNation1, 300);
  const [debouncedInputNation2] = useDebouncedValue(inputNation2, 300);

  const { data: inputNation1Options = [] } = useQuery({
    queryKey: ["nation-search", debouncedInputNation1],
    queryFn: () =>
      debouncedInputNation1.length >= 1
        ? searchNations(debouncedInputNation1, 15)
        : Promise.resolve([]),
    enabled: debouncedInputNation1.length >= 1,
  });

  const { data: inputNation2Options = [] } = useQuery({
    queryKey: ["nation-search", debouncedInputNation2],
    queryFn: () =>
      debouncedInputNation2.length >= 1
        ? searchNations(debouncedInputNation2, 15)
        : Promise.resolve([]),
    enabled: debouncedInputNation2.length >= 1,
  });
  const { data: linkedNationData, isFetched: linkedNationFetched } = useQuery({
    queryKey: ["linkedNation"],
    queryFn: async () => {
      try {
        return await getLinkedNation();
      } catch {
        return null;
      }
    },
    retry: false,
  });

  const showLinkedWarPresets = Boolean(
    linkedNationData?.linked && linkedNationData?.nation_id,
  );

  const linkedWarsQuery = useQuery<DamageLinkedActiveWarsResponse>({
    queryKey: ["damage-linked-wars", linkedNationData?.nation_id],
    queryFn: fetchLinkedActiveWars,
    enabled: showLinkedWarPresets,
    staleTime: 120_000,
    retry: false,
  });

  const onSelectLinkedWar = useCallback(
    (w: DamageLinkedWarPreset) => {
      const raw = linkedNationData?.nation_id;
      const linkedId =
        raw != null && String(raw).trim() !== ""
          ? Number(String(raw).trim())
          : NaN;
      if (!Number.isFinite(linkedId) || linkedId <= 0) return;
      navigate(`/damage?nation1=${linkedId}&nation2=${w.opponent_id}`);
    },
    [navigate, linkedNationData?.nation_id],
  );

  const inputNation1OptionsData = useMemo(
    () =>
      inputNation1Options.slice(0, 6).map((option) => ({
        value: option.label,
        label: option.label,
      })),
    [inputNation1Options],
  );

  const inputNation2OptionsData = useMemo(
    () =>
      inputNation2Options.slice(0, 6).map((option) => ({
        value: option.label,
        label: option.label,
      })),
    [inputNation2Options],
  );

  useEffect(() => {
    if (nation1) return;
    if (hasTouchedNation1Input) return;
    const linkedNationId = linkedNationData?.linked
      ? linkedNationData.nation_id || ""
      : "";
    if (!linkedNationId) return;
    if (inputNation1.trim()) return;
    const parsed = parseNationIdInput(linkedNationId);
    if (!parsed) return;
    setInputNation1(String(parsed));
    setNation1Query(String(parsed));
    form.setFieldValue("nation1Id", parsed);
  }, [
    nation1,
    hasTouchedNation1Input,
    linkedNationData?.linked,
    linkedNationData?.nation_id,
    inputNation1,
    form,
  ]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const nation1Id = await resolveNationId(inputNation1);
    const nation2Id = await resolveNationId(inputNation2);
    if (nation1Id && nation2Id) {
      navigate(`/damage?nation1=${nation1Id}&nation2=${nation2Id}`);
    }
  };

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["damage", nation1, nation2],
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
    setNation1Query(form.values.nation1Id ? String(form.values.nation1Id) : "");
    setNation2Query(form.values.nation2Id ? String(form.values.nation2Id) : "");
  }, [form.values.nation1Id, form.values.nation2Id]);

  const commitNation1Query = useCallback(
    (value: string) => {
      setNation1Query(value);
      form.setFieldValue("nation1Id", parseNationIdInput(value));
    },
    [form],
  );

  const commitNation2Query = useCallback(
    (value: string) => {
      setNation2Query(value);
      form.setFieldValue("nation2Id", parseNationIdInput(value));
    },
    [form],
  );

  const activeData = calculatedData ?? data ?? null;

  const handleCalculate = async () => {
    setFormError(null);
    setIsCalculating(true);
    try {
      const resolvedNation1 =
        form.values.nation1Id || (await resolveNationId(nation1Query));
      const resolvedNation2 =
        form.values.nation2Id || (await resolveNationId(nation2Query));
      if (!resolvedNation1 || !resolvedNation2) {
        setFormError(
          "Please provide valid nation IDs or select from the autocomplete list.",
        );
        setIsCalculating(false);
        return;
      }
      form.setFieldValue("nation1Id", resolvedNation1);
      form.setFieldValue("nation2Id", resolvedNation2);

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
      const message =
        err instanceof Error ? err.message : "Failed to calculate damage";
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

          {linkedNationFetched && !linkedNationData?.linked ? (
            <DamageDiscordPerkPromo />
          ) : null}

          <Paper p="md" withBorder>
            <form onSubmit={handleSubmit}>
              <Stack gap="md">
                <Text size="sm" c="dimmed">
                  Enter two nation IDs to calculate damage potential
                </Text>
                <Flex
                  direction={{ base: "column", sm: "row" }}
                  gap="sm"
                  align={{ base: "stretch", sm: "flex-end" }}
                  wrap="nowrap"
                >
                  <Autocomplete
                    placeholder="Nation 1 ID, name, or leader"
                    size="sm"
                    flex={{ sm: 1 }}
                    miw={{ sm: 0 }}
                    value={inputNation1}
                    onChange={(value) => {
                      setHasTouchedNation1Input(true);
                      setInputNation1(value);
                    }}
                    leftSection={<IconSearch size={16} />}
                    data={inputNation1OptionsData}
                    limit={6}
                    onOptionSubmit={(value) => {
                      setHasTouchedNation1Input(true);
                      setInputNation1(value);
                    }}
                  />
                  <Autocomplete
                    placeholder="Nation 2 ID, name, or leader"
                    size="sm"
                    flex={{ sm: 1 }}
                    miw={{ sm: 0 }}
                    value={inputNation2}
                    onChange={setInputNation2}
                    leftSection={<IconSearch size={16} />}
                    data={inputNation2OptionsData}
                    limit={6}
                    onOptionSubmit={(value) => setInputNation2(value)}
                  />
                  <Button
                    type="submit"
                    size="sm"
                    leftSection={<IconCalculator size={20} />}
                    disabled={!inputNation1.trim() || !inputNation2.trim()}
                  >
                    Calculate Damage
                  </Button>
                </Flex>
              </Stack>
            </form>
          </Paper>

          {showLinkedWarPresets ? (
            <Paper p="md" withBorder>
              <DamageWarPresetsSection
                wars={linkedWarsQuery.data?.wars ?? []}
                isLoading={linkedWarsQuery.isLoading}
                isError={linkedWarsQuery.isError}
                error={linkedWarsQuery.error}
                onRetry={() => void linkedWarsQuery.refetch()}
                onSelectWar={onSelectLinkedWar}
              />
            </Paper>
          ) : null}

          <Stack gap="md">
            <Title order={2}>Damage Analysis</Title>
            <Text c="dimmed">
              Enter nation IDs above to see damage calculations
            </Text>

            <DamagePageSkeleton />
          </Stack>
        </Stack>
      </Container>
    );
  }

  if (isLoading) {
    return (
      <Container size="xl" py="md">
        <Stack gap="md">
          <DamageCalculatorPageHeader />

          <Paper p="lg" withBorder radius="md">
            <Stack gap="lg">
              <div>
                <Title order={3}>Damage Inputs</Title>
                <Text size="sm" c="dimmed">
                  Adjust the assumptions below and re-run the calculator with
                  custom inputs.
                </Text>
              </div>

              <DamageNationSearchRow
                form={form}
                nation1Query={nation1Query}
                nation2Query={nation2Query}
                onCommitNation1={(value) => {
                  setHasTouchedNation1Input(true);
                  commitNation1Query(value);
                }}
                onCommitNation2={commitNation2Query}
              />

              {showLinkedWarPresets ? (
                <Paper p="md" withBorder radius="md">
                  <DamageWarPresetsSection
                    wars={linkedWarsQuery.data?.wars ?? []}
                    isLoading={linkedWarsQuery.isLoading}
                    isError={linkedWarsQuery.isError}
                    error={linkedWarsQuery.error}
                    onRetry={() => void linkedWarsQuery.refetch()}
                    onSelectWar={onSelectLinkedWar}
                    selectedNation1Id={parsedNation1}
                    selectedNation2Id={parsedNation2}
                  />
                </Paper>
              ) : null}

              <Paper p="md" withBorder radius="md">
                <Group gap="sm" wrap="nowrap">
                  <Loader size="sm" />
                  <Text size="sm" c="dimmed">
                    Loading nation stats and form defaults…
                  </Text>
                </Group>
              </Paper>
            </Stack>
          </Paper>

          <Paper p="lg" withBorder radius="md">
            <DamagePageSkeleton variant="results" animated />
          </Paper>
        </Stack>
      </Container>
    );
  }

  if (error && !activeData) {
    const apiError = error as unknown as ApiError;

    return (
      <ErrorState
        title="Failed to load damage data"
        message={apiError.message || "An unexpected error occurred"}
        onRetry={() => refetch()}
      />
    );
  }

  if (!activeData) {
    return <ErrorState title="No data" message="No damage data available" />;
  }

  const nation1Label = activeData.nations.nation1.nationName || "Nation 1";
  const nation2Label = activeData.nations.nation2.nationName || "Nation 2";
  const nation1CityCount = activeData.nations.nation1.numCities ?? 0;
  const nation2CityCount = activeData.nations.nation2.numCities ?? 0;
  const baselineNation1Units = data?.inputs?.nation1;
  const baselineNation2Units = data?.inputs?.nation2;
  const attackerName =
    form.values.war.attackerId === form.values.nation2Id
      ? nation2Label
      : nation1Label;
  const defenderName =
    attackerName === nation1Label ? nation2Label : nation1Label;
  const warTypeDescription = WAR_TYPE_OPTIONS.find(
    (option) => option.value === form.values.war.warType,
  )?.description;
  const warPolicyDescriptions = Object.fromEntries(
    WAR_POLICY_OPTIONS.map((option) => [option.value, option.description]),
  );

  return (
    <Container size="xl" py="md">
      <Stack gap="md">
        <DamageCalculatorPageHeader />

        <Paper p="lg" withBorder radius="md">
          <form onSubmit={form.onSubmit(handleCalculate)}>
            <Stack gap="lg">
              <div>
                <Title order={3}>Damage Inputs</Title>
                <Text size="sm" c="dimmed">
                  Adjust the assumptions below and re-run the calculator with
                  custom inputs.
                </Text>
              </div>

              <DamageNationSearchRow
                form={form}
                nation1Query={nation1Query}
                nation2Query={nation2Query}
                onCommitNation1={(value) => {
                  setHasTouchedNation1Input(true);
                  commitNation1Query(value);
                }}
                onCommitNation2={commitNation2Query}
              />

              {showLinkedWarPresets ? (
                <Paper p="md" withBorder radius="md">
                  <DamageWarPresetsSection
                    wars={linkedWarsQuery.data?.wars ?? []}
                    isLoading={linkedWarsQuery.isLoading}
                    isError={linkedWarsQuery.isError}
                    error={linkedWarsQuery.error}
                    onRetry={() => void linkedWarsQuery.refetch()}
                    onSelectWar={onSelectLinkedWar}
                    selectedNation1Id={parsedNation1}
                    selectedNation2Id={parsedNation2}
                  />
                </Paper>
              ) : null}

              <Grid gutter="lg">
                <Grid.Col span={{ base: 12, md: 6 }}>
                  <Paper p="md" withBorder radius="md">
                    <Stack gap="sm">
                      <Text size="sm" fw={600}>
                        {nation1Label}
                      </Text>
                      <NationUnitPlanner
                        form={form}
                        basePath="nation1"
                        initialCityCount={nation1CityCount}
                        baselineUnits={baselineNation1Units}
                      />
                      <Select
                        label="War Policy"
                        data={WAR_POLICY_OPTIONS}
                        searchable
                        maxDropdownHeight={320}
                        renderOption={({ option }) => {
                          const details = option as {
                            label: string;
                            description?: string;
                          };
                          return (
                            <div>
                              <Text fw={600} size="sm">
                                {details.label}
                              </Text>
                              <Text
                                size="xs"
                                c="dimmed"
                                style={{
                                  whiteSpace: "normal",
                                  lineHeight: 1.35,
                                }}
                              >
                                {details.description}
                              </Text>
                            </div>
                          );
                        }}
                        {...form.getInputProps("nation1.warpolicy")}
                      />
                      {form.values.nation1.warpolicy && (
                        <Text size="xs" c="dimmed">
                          {warPolicyDescriptions[form.values.nation1.warpolicy]}
                        </Text>
                      )}
                      <NationDamageModifiers form={form} basePath="nation1" />
                    </Stack>
                  </Paper>
                </Grid.Col>

                <Grid.Col span={{ base: 12, md: 6 }}>
                  <Paper p="md" withBorder radius="md">
                    <Stack gap="sm">
                      <Text size="sm" fw={600}>
                        {nation2Label}
                      </Text>
                      <NationUnitPlanner
                        form={form}
                        basePath="nation2"
                        initialCityCount={nation2CityCount}
                        baselineUnits={baselineNation2Units}
                      />
                      <Select
                        label="War Policy"
                        data={WAR_POLICY_OPTIONS}
                        searchable
                        maxDropdownHeight={320}
                        renderOption={({ option }) => {
                          const details = option as {
                            label: string;
                            description?: string;
                          };
                          return (
                            <div>
                              <Text fw={600} size="sm">
                                {details.label}
                              </Text>
                              <Text
                                size="xs"
                                c="dimmed"
                                style={{
                                  whiteSpace: "normal",
                                  lineHeight: 1.35,
                                }}
                              >
                                {details.description}
                              </Text>
                            </div>
                          );
                        }}
                        {...form.getInputProps("nation2.warpolicy")}
                      />
                      {form.values.nation2.warpolicy && (
                        <Text size="xs" c="dimmed">
                          {warPolicyDescriptions[form.values.nation2.warpolicy]}
                        </Text>
                      )}
                      <NationDamageModifiers form={form} basePath="nation2" />
                    </Stack>
                  </Paper>
                </Grid.Col>
              </Grid>

              <Paper p="md" withBorder radius="md">
                <Stack gap="sm">
                  <Text size="sm" fw={600}>
                    War State
                  </Text>
                  <Select
                    label="War Type"
                    data={WAR_TYPE_OPTIONS}
                    value={form.values.war.warType}
                    onChange={(value) =>
                      form.setFieldValue(
                        "war.warType",
                        (value as DamageWarType) || "ORDINARY",
                      )
                    }
                  />
                  {warTypeDescription && (
                    <Text size="xs" c="dimmed">
                      {warTypeDescription}
                    </Text>
                  )}
                  <Text size="sm" fw={600}>
                    Attacker Selection
                  </Text>
                  <Text size="xs" c="dimmed">
                    Choose the war attacker (the nation that declared the war)
                    and the war defender. This affects war type and war policy
                    modifiers. It is separate from which side is making a
                    specific attack in the tables below.
                  </Text>
                  <SegmentedControl
                    fullWidth
                    value={String(
                      form.values.war.attackerId || form.values.nation1Id,
                    )}
                    onChange={(value) => {
                      const attackerId = Number(value);
                      const defenderId =
                        attackerId === form.values.nation1Id
                          ? form.values.nation2Id
                          : form.values.nation1Id;
                      form.setFieldValue("war.attackerId", attackerId);
                      form.setFieldValue("war.defenderId", defenderId);
                    }}
                    data={buildNationOptions(
                      form.values.nation1Id,
                      form.values.nation2Id,
                      nation1Label,
                      nation2Label,
                    )}
                  />
                  <Divider my="sm" />

                  <Group grow>
                    <Select
                      label="Air Superiority"
                      value={
                        form.values.war.airSuperiorityId
                          ? String(form.values.war.airSuperiorityId)
                          : "none"
                      }
                      onChange={(value) =>
                        form.setFieldValue(
                          "war.airSuperiorityId",
                          value === "none" ? null : Number(value),
                        )
                      }
                      data={buildNationOptions(
                        form.values.nation1Id,
                        form.values.nation2Id,
                        nation1Label,
                        nation2Label,
                        true,
                      )}
                    />
                  </Group>

                  <Group grow>
                    <Switch
                      label={`Fortified (${attackerName})`}
                      description="Apply fortified modifier to the attacker."
                      checked={form.values.war.attackerFortified}
                      onChange={(event) =>
                        form.setFieldValue(
                          "war.attackerFortified",
                          event.currentTarget.checked,
                        )
                      }
                    />
                    <Switch
                      label={`Fortified (${defenderName})`}
                      description="Apply fortified modifier to the defender."
                      checked={form.values.war.defenderFortified}
                      onChange={(event) =>
                        form.setFieldValue(
                          "war.defenderFortified",
                          event.currentTarget.checked,
                        )
                      }
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
                  size="sm"
                  leftSection={
                    isCalculating ? (
                      <Loader size="xs" />
                    ) : (
                      <IconCalculator size={20} />
                    )
                  }
                  loading={isCalculating}
                  fullWidth
                >
                  Recalculate Damage
                </Button>
              </Group>
            </Stack>
          </form>
        </Paper>
        <Paper p="lg" withBorder radius="md">
          <DamageDashboard data={activeData} />
        </Paper>
      </Stack>
    </Container>
  );
}
