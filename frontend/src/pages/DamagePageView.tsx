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
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useQuery } from "@tanstack/react-query";
import { IconSearch, IconCalculator } from "@tabler/icons-react";
import { useDebouncedValue } from "@mantine/hooks";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";

import { calculateDamage, fetchDamage, searchNations } from "@/api";
import { getLinkedNation } from "@/api/auth";
import { DamageDashboard } from "@/components/damage";
import { LoadingState, ErrorState } from "@/components/common";
import type {
  ApiError,
  DamageCalculationInput,
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
  const { data: linkedNationData } = useQuery({
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

          <Paper p="md" withBorder>
            <form onSubmit={handleSubmit}>
              <Stack gap="md">
                <Text size="sm" c="dimmed">
                  Enter two nation IDs to calculate damage potential
                </Text>
                <Group grow>
                  <Autocomplete
                    placeholder="Nation 1 ID, name, or leader"
                    size="sm"
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
                </Group>
              </Stack>
            </form>
          </Paper>

          <Stack gap="md">
            <Title order={2}>Damage Analysis</Title>
            <Text c="dimmed">
              Enter nation IDs above to see damage calculations
            </Text>

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
                  Adjust the assumptions below and re-run the calculator with
                  custom inputs.
                </Text>
              </div>

              <Paper p="md" withBorder radius="md">
                <Stack gap="sm">
                  <Group grow align="flex-end">
                    <NationAutocompleteField
                      label="Nation 1 ID, name, or leader"
                      value={nation1Query}
                      onCommit={(value) => {
                        setHasTouchedNation1Input(true);
                        commitNation1Query(value);
                      }}
                    />
                    <NationAutocompleteField
                      label="Nation 2 ID, name, or leader"
                      value={nation2Query}
                      onCommit={commitNation2Query}
                    />
                    <Button
                      variant="light"
                      type="button"
                      style={{ alignSelf: "flex-end" }}
                      onClick={async () => {
                        const nation1Id =
                          form.values.nation1Id ||
                          (await resolveNationId(nation1Query));
                        const nation2Id =
                          form.values.nation2Id ||
                          (await resolveNationId(nation2Query));
                        if (nation1Id && nation2Id) {
                          navigate(
                            `/damage?nation1=${nation1Id}&nation2=${nation2Id}`,
                          );
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
