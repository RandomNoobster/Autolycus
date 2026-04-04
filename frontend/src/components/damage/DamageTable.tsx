/**
 * Damage Table Component
 *
 * Table showing detailed attack statistics.
 */

import { useCallback, useMemo, useState } from 'react';
import {
  MantineReactTable,
  useMantineReactTable,
  type MRT_ColumnDef,
  type MRT_VisibilityState,
} from 'mantine-react-table';
import { Box, Center, Group, Text, UnstyledButton } from '@mantine/core';
import { IconChevronDown } from '@tabler/icons-react';

import type { AttackStats, ResourceType } from '@/types';
import { useTablePersistence } from '@/hooks';
import { ResourceIcon } from '@/components/common';

import {
  type NationSlot,
  getCostClusterTheme,
  headTintForSlot,
  nationSlotForId,
} from './damageNationTheme';

interface DamageTableProps {
  attackerName: string;
  defenderName: string;
  attackerNationId: number;
  defenderNationId: number;
  nation1Id: number;
  attackerData: AttackStats[];
  defenderData: AttackStats[];
}

type CostRole = 'attacker' | 'defender';

const ATTACKER_BREAKDOWN_ACCESSORS = [
  'attackerGas',
  'attackerMun',
  'attackerSteel',
  'attackerAlum',
  'attackerUranium',
  'attackerMoney',
] as const;

const DEFENDER_BREAKDOWN_ACCESSORS = [
  'defenderGas',
  'defenderMun',
  'defenderSteel',
  'defenderAlum',
  'defenderUranium',
  'defenderMoney',
  'defenderInfra',
] as const;

function mergeDamageColumnVisibility(
  persisted: MRT_VisibilityState,
  attackerOpen: boolean,
  defenderOpen: boolean,
): MRT_VisibilityState {
  const v: MRT_VisibilityState = { ...persisted };
  for (const key of ATTACKER_BREAKDOWN_ACCESSORS) {
    v[key] = attackerOpen;
  }
  for (const key of DEFENDER_BREAKDOWN_ACCESSORS) {
    v[key] = defenderOpen;
  }
  return v;
}

function stripCostBreakdownVisibilityKeys(
  visibility: MRT_VisibilityState,
): MRT_VisibilityState {
  const next = { ...visibility };
  for (const key of ATTACKER_BREAKDOWN_ACCESSORS) {
    delete next[key];
  }
  for (const key of DEFENDER_BREAKDOWN_ACCESSORS) {
    delete next[key];
  }
  return next;
}

/** Match raids table body cell padding (dense rows). */
const DAMAGE_BODY_CELL_PAD = {
  paddingTop: 2,
  paddingBottom: 2,
  paddingLeft: 6,
  paddingRight: 6,
} as const;

const DAMAGE_HEAD_CELL_PAD = {
  padding: '2px 4px',
  verticalAlign: 'bottom' as const,
};

/** Roomier padding inside the cost cluster (Away from accent rails / dividers). */
const COST_CLUSTER_HEAD_PAD = {
  paddingTop: 5,
  paddingBottom: 5,
  paddingLeft: 12,
  paddingRight: 12,
  verticalAlign: 'bottom' as const,
};

const COST_CLUSTER_BODY_PAD = {
  paddingTop: 3,
  paddingBottom: 3,
  paddingLeft: 12,
  paddingRight: 12,
} as const;

/** Column directly left of Cost — extra space before the shared edge. */
const PRE_COST_HEAD_PAD = {
  ...COST_CLUSTER_HEAD_PAD,
  paddingRight: COST_CLUSTER_HEAD_PAD.paddingRight + 10,
};

const PRE_COST_BODY_PAD = {
  ...COST_CLUSTER_BODY_PAD,
  paddingRight: COST_CLUSTER_BODY_PAD.paddingRight + 10,
};

/** Breakdown cells with an inner vertical rule need a touch more left inset. */
const BREAKDOWN_INNER_HEAD_PAD = {
  ...COST_CLUSTER_HEAD_PAD,
  paddingLeft: COST_CLUSTER_HEAD_PAD.paddingLeft + 4,
};

const BREAKDOWN_INNER_BODY_PAD = {
  ...COST_CLUSTER_BODY_PAD,
  paddingLeft: COST_CLUSTER_BODY_PAD.paddingLeft + 4,
};

/**
 * Cost block wash: `fixed` ties every cell in the cluster to one viewport-aligned gradient
 * (same trick as thead). Per-cell `cover` + scroll looked like repeating ribs per column.
 * Row/cell transitions are disabled on `.damage-mrt-table` to keep hover repaints tolerable.
 */
function costClusterHeadSurface(cluster: ReturnType<typeof getCostClusterTheme>) {
  return {
    backgroundImage: cluster.sectionWash,
    backgroundAttachment: 'fixed' as const,
    backgroundSize: 'cover' as const,
    backgroundRepeat: 'no-repeat' as const,
  };
}

function costClusterBodySurface(cluster: ReturnType<typeof getCostClusterTheme>) {
  return {
    backgroundImage: cluster.sectionWash,
    backgroundAttachment: 'fixed' as const,
    backgroundSize: 'cover' as const,
    backgroundRepeat: 'no-repeat' as const,
  };
}

/* Up to 2 lines, centered; overflow ellipsis on second line (see .damage-mrt-table thead in index.css). */
const wrappedHeader = (text: string) => (
  <Box
    style={{
      display: '-webkit-box',
      WebkitBoxOrient: 'vertical',
      WebkitLineClamp: 2,
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'normal',
      wordWrap: 'break-word',
      overflowWrap: 'break-word',
      textAlign: 'center',
      lineHeight: 1.25,
      width: '100%',
      minWidth: 0,
    }}
  >
    {text}
  </Box>
);

/** Resource column: icon only in the header (label via title / aria-label for a11y). */
const shortResourceHeader = (resource: ResourceType, accessibleLabel: string) => (
  <Center w="100%" miw={0} py={2} title={accessibleLabel}>
    <Box
      component="span"
      style={{ lineHeight: 0 }}
      aria-label={accessibleLabel}
    >
      <ResourceIcon resource={resource} showValue={false} size={16} />
    </Box>
  </Center>
);

function costBreakdownGroupLabel(nationName: string) {
  return `${nationName} Cost Breakdown`;
}

/**
 * Parent group header only (TanStack renders this in the row above the Cost leaf).
 * Keeps sort / column menu on the Cost leaf row so they align with other columns.
 */
const costBreakdownToggleGroupHeader = (
  nationName: string,
  expanded: boolean,
  onToggle: () => void,
) => {
  const toggleLabel = expanded
    ? `Hide ${costBreakdownGroupLabel(nationName)}`
    : `Show ${costBreakdownGroupLabel(nationName)}`;

  return (
    <UnstyledButton
      className="damage-cost-breakdown-toggle"
      aria-expanded={expanded}
      aria-label={toggleLabel}
      onClick={(e) => {
        e.stopPropagation();
        onToggle();
      }}
      style={{
        width: '100%',
        maxWidth: '100%',
        borderRadius: 4,
        color: 'inherit',
      }}
    >
      <Group gap={6} wrap="nowrap" justify="center" align="center" w="100%" miw={0} py={2}>
        <Text
          component="span"
          size="xs"
          fw={600}
          c="dimmed"
          style={{
            textAlign: 'center',
            lineHeight: 1.25,
            maxWidth: '100%',
          }}
          lineClamp={2}
        >
          {costBreakdownGroupLabel(nationName)}
        </Text>
        <Box
          component="span"
          aria-hidden
          className="damage-cost-breakdown-chevron"
          data-expanded={expanded ? 'true' : 'false'}
          style={{
            flexShrink: 0,
            color: 'rgba(255, 255, 255, 0.55)',
            lineHeight: 0,
            display: 'flex',
          }}
        >
          <IconChevronDown size={18} />
        </Box>
      </Group>
    </UnstyledButton>
  );
};

interface CombinedAttackRow {
  attackType: string;
  label: string;
  netDamage: number;
  // What it costs the attacking nation (military losses + resources)
  attackerCost: number;     // attacker's military losses (damageReceived from attacker's data)
  attackerGas: number;
  attackerMun: number;
  attackerSteel: number;
  attackerAlum: number;
  attackerUranium: number;
  attackerMoney: number;
  // What it costs the defending nation (military losses + infra + resources)
  defenderCost: number;     // defender's military losses = attacker's damageDealt
  defenderGas: number;
  defenderMun: number;
  defenderSteel: number;
  defenderAlum: number;
  defenderUranium: number;
  defenderMoney: number;
  defenderInfra: number;    // infra value defender loses = attacker's infraDestroyed
}

function wrapWarPartyBreakdownGroup(
  role: CostRole,
  nationSlot: NationSlot,
  partyName: string,
  sectionStart: boolean,
  breakdownExpanded: boolean,
  onBreakdownToggle: () => void,
  leaves: MRT_ColumnDef<CombinedAttackRow>[],
): MRT_ColumnDef<CombinedAttackRow>[] {
  const cellTint = headTintForSlot(nationSlot);
  const cluster = getCostClusterTheme(nationSlot);
  const sectionDividerHead = sectionStart
    ? {}
    : { borderLeft: cluster.interNationDividerLeft };

  /** Attacker group: soften right seam vs defender. Defender group: soften left seam; keep strong outer right rail. */
  const mergedBreakdownGroupHeadStyle = sectionStart
    ? {
        ...COST_CLUSTER_HEAD_PAD,
        ...cellTint,
        ...costClusterHeadSurface(cluster),
        verticalAlign: 'middle' as const,
        borderLeft: cluster.interNationDividerLeft,
        borderRight: cluster.interNationBorderRight,
        boxShadow: `${cluster.interNationRailInsetLeft}, ${cluster.interNationRailClose}`,
      }
    : {
        ...COST_CLUSTER_HEAD_PAD,
        ...cellTint,
        ...costClusterHeadSurface(cluster),
        verticalAlign: 'middle' as const,
        ...sectionDividerHead,
        borderRight: cluster.breakdownGroupHeadRight,
        boxShadow: `${cluster.interNationRailInsetLeft}, ${cluster.railClose}`,
      };

  return [
    {
      id: `${role}CostBreakdownHeaderGroup`,
      header: costBreakdownGroupLabel(partyName),
      Header: () =>
        costBreakdownToggleGroupHeader(
          partyName,
          breakdownExpanded,
          onBreakdownToggle,
        ),
      enableSorting: false,
      enableColumnActions: false,
      enableHiding: false,
      columns: leaves,
      mantineTableHeadCellProps: {
        className: 'damage-cost-breakdown-group-head',
        style: mergedBreakdownGroupHeadStyle,
      },
    },
  ];
}

function buildWarPartyBreakdownLeaves(
  role: CostRole,
  nationSlot: NationSlot,
  partyName: string,
  sectionStart: boolean,
  breakdownExpanded: boolean,
): MRT_ColumnDef<CombinedAttackRow>[] {
  const cellTint = headTintForSlot(nationSlot);
  const cluster = getCostClusterTheme(nationSlot);
  const costKey: keyof CombinedAttackRow = role === 'attacker' ? 'attackerCost' : 'defenderCost';

  const gasKey: keyof CombinedAttackRow = role === 'attacker' ? 'attackerGas' : 'defenderGas';
  const munKey: keyof CombinedAttackRow = role === 'attacker' ? 'attackerMun' : 'defenderMun';
  const steelKey: keyof CombinedAttackRow = role === 'attacker' ? 'attackerSteel' : 'defenderSteel';
  const alumKey: keyof CombinedAttackRow = role === 'attacker' ? 'attackerAlum' : 'defenderAlum';
  const uraniumKey: keyof CombinedAttackRow = role === 'attacker' ? 'attackerUranium' : 'defenderUranium';
  const moneyKey: keyof CombinedAttackRow = role === 'attacker' ? 'attackerMoney' : 'defenderMoney';

  /** First column of defender block: soft seam vs attacker cost columns. */
  const sectionDividerHead = sectionStart
    ? {}
    : { borderLeft: cluster.interNationDividerLeft };
  const sectionDividerBody = sectionStart
    ? {}
    : { borderLeft: cluster.interNationDividerLeft };

  const lastBreakdownHeadExtra =
    role === 'defender'
      ? {}
      : {
          borderRight: cluster.interNationBorderRight,
          boxShadow: cluster.interNationRailClose,
        };

  const costHeaderLabel = `${partyName} Cost`;
  const sumHeaderLabel = `${partyName} Sum`;

  /**
   * Collapsed: outer vertical seam between nations uses interNation* (thinner / lower contrast).
   * Defender Cost: left matches nation seam. Attacker Cost: left matches same seam vs Net Dealt;
   * right matches seam vs defender Cost.
   */
  const costLeafEdgeChrome =
    role === 'defender'
      ? breakdownExpanded
        ? {
            boxShadow: cluster.interNationRailInsetLeft,
            borderRight: cluster.innerRule,
          }
        : {
            boxShadow: `${cluster.interNationRailInsetLeft}, ${cluster.railClose}`,
            borderRight: cluster.breakdownGroupHeadRight,
          }
      : breakdownExpanded
        ? {
            borderLeft: cluster.interNationDividerLeft,
            boxShadow: cluster.interNationRailInsetLeft,
            borderRight: cluster.innerRule,
          }
        : {
            borderLeft: cluster.interNationDividerLeft,
            boxShadow: `${cluster.interNationRailInsetLeft}, ${cluster.interNationRailClose}`,
            borderRight: cluster.interNationBorderRight,
          };

  const costLeafColumn = {
    accessorKey: costKey,
    header: breakdownExpanded ? sumHeaderLabel : costHeaderLabel,
    Header: () =>
      breakdownExpanded ? wrappedHeader('Sum') : wrappedHeader(costHeaderLabel),
    size: 120,
    mantineTableBodyCellProps: () => ({
      fz: 'sm',
      style: {
        ...PRE_COST_BODY_PAD,
        textAlign: 'right',
        ...cellTint,
        ...costClusterBodySurface(cluster),
        ...costLeafEdgeChrome,
        ...sectionDividerBody,
      },
    }),
    mantineTableHeadCellProps: {
      style: {
        ...PRE_COST_HEAD_PAD,
        ...cellTint,
        ...costClusterHeadSurface(cluster),
        ...costLeafEdgeChrome,
        ...sectionDividerHead,
        verticalAlign: 'bottom' as const,
      },
    },
    Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
  } satisfies MRT_ColumnDef<CombinedAttackRow>;

  const breakdownLeafColumns: MRT_ColumnDef<CombinedAttackRow>[] = [
    costLeafColumn,
    {
      accessorKey: gasKey,
      header: 'Gasoline',
      Header: () => shortResourceHeader('gasoline', 'Gasoline'),
      enableHiding: false,
      size: 50,
      mantineTableBodyCellProps: {
        fz: 'sm',
        style: {
          ...COST_CLUSTER_BODY_PAD,
          textAlign: 'right',
          ...cellTint,
          ...costClusterBodySurface(cluster),
        },
      },
      mantineTableHeadCellProps: {
        style: {
          ...COST_CLUSTER_HEAD_PAD,
          ...cellTint,
          ...costClusterHeadSurface(cluster),
          verticalAlign: 'bottom' as const,
        },
      },
      Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
    },
    {
      accessorKey: munKey,
      header: 'Munitions',
      Header: () => shortResourceHeader('munitions', 'Munitions'),
      enableHiding: false,
      size: 50,
      mantineTableBodyCellProps: {
        fz: 'sm',
        style: {
          ...BREAKDOWN_INNER_BODY_PAD,
          textAlign: 'right',
          ...cellTint,
          ...costClusterBodySurface(cluster),
          borderLeft: cluster.innerRule,
        },
      },
      mantineTableHeadCellProps: {
        style: {
          ...BREAKDOWN_INNER_HEAD_PAD,
          ...cellTint,
          ...costClusterHeadSurface(cluster),
          borderLeft: cluster.innerRule,
          verticalAlign: 'bottom' as const,
        },
      },
      Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
    },
    {
      accessorKey: steelKey,
      header: 'Steel',
      Header: () => shortResourceHeader('steel', 'Steel'),
      enableHiding: false,
      size: 50,
      mantineTableBodyCellProps: {
        fz: 'sm',
        style: {
          ...BREAKDOWN_INNER_BODY_PAD,
          textAlign: 'right',
          ...cellTint,
          ...costClusterBodySurface(cluster),
          borderLeft: cluster.innerRule,
        },
      },
      mantineTableHeadCellProps: {
        style: {
          ...BREAKDOWN_INNER_HEAD_PAD,
          ...cellTint,
          ...costClusterHeadSurface(cluster),
          borderLeft: cluster.innerRule,
          verticalAlign: 'bottom' as const,
        },
      },
      Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
    },
    {
      accessorKey: alumKey,
      header: 'Aluminum',
      Header: () => shortResourceHeader('aluminum', 'Aluminum'),
      enableHiding: false,
      size: 50,
      mantineTableBodyCellProps: {
        fz: 'sm',
        style: {
          ...BREAKDOWN_INNER_BODY_PAD,
          textAlign: 'right',
          ...cellTint,
          ...costClusterBodySurface(cluster),
          borderLeft: cluster.innerRule,
        },
      },
      mantineTableHeadCellProps: {
        style: {
          ...BREAKDOWN_INNER_HEAD_PAD,
          ...cellTint,
          ...costClusterHeadSurface(cluster),
          borderLeft: cluster.innerRule,
          verticalAlign: 'bottom' as const,
        },
      },
      Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
    },
    {
      accessorKey: uraniumKey,
      header: 'Uranium',
      Header: () => shortResourceHeader('uranium', 'Uranium'),
      enableHiding: false,
      size: 50,
      mantineTableBodyCellProps: {
        fz: 'sm',
        style: {
          ...BREAKDOWN_INNER_BODY_PAD,
          textAlign: 'right',
          ...cellTint,
          ...costClusterBodySurface(cluster),
          borderLeft: cluster.innerRule,
        },
      },
      mantineTableHeadCellProps: {
        style: {
          ...BREAKDOWN_INNER_HEAD_PAD,
          ...cellTint,
          ...costClusterHeadSurface(cluster),
          borderLeft: cluster.innerRule,
          verticalAlign: 'bottom' as const,
        },
      },
      Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
    },
    {
      accessorKey: moneyKey,
      header: 'Cash',
      Header: () => shortResourceHeader('money', 'Cash'),
      enableHiding: false,
      size: 100,
      mantineTableBodyCellProps: {
        fz: 'sm',
        style: {
          ...BREAKDOWN_INNER_BODY_PAD,
          textAlign: 'right',
          ...cellTint,
          ...costClusterBodySurface(cluster),
          borderLeft: cluster.innerRule,
          ...(role === 'defender'
            ? {}
            : {
                borderRight: cluster.interNationBorderRight,
                boxShadow: cluster.interNationRailClose,
              }),
        },
      },
      mantineTableHeadCellProps: {
        style: {
          ...BREAKDOWN_INNER_HEAD_PAD,
          ...cellTint,
          ...costClusterHeadSurface(cluster),
          borderLeft: cluster.innerRule,
          verticalAlign: 'bottom' as const,
          ...(role === 'defender' ? {} : lastBreakdownHeadExtra),
        },
      },
      Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
    },
    ...(role === 'defender'
      ? [
          {
            accessorKey: 'defenderInfra' as const,
            header: 'Infra Damage',
            Header: () => wrappedHeader('Infra Damage'),
            enableHiding: false,
            size: 130,
            mantineTableBodyCellProps: {
              fz: 'sm',
              style: {
                ...BREAKDOWN_INNER_BODY_PAD,
                textAlign: 'right',
                ...cellTint,
                ...costClusterBodySurface(cluster),
                borderLeft: cluster.innerRule,
                boxShadow: cluster.railClose,
              },
            },
            mantineTableHeadCellProps: {
              style: {
                ...BREAKDOWN_INNER_HEAD_PAD,
                ...cellTint,
                ...costClusterHeadSurface(cluster),
                borderLeft: cluster.innerRule,
                verticalAlign: 'bottom' as const,
                borderRight: cluster.breakdownGroupHeadRight,
                boxShadow: cluster.railClose,
              },
            },
            Cell: ({ cell }) => `$${(cell.getValue() as number).toLocaleString()}`,
          } satisfies MRT_ColumnDef<CombinedAttackRow>,
        ]
      : []),
  ];

  return breakdownLeafColumns;
}

export function DamageTable({
  attackerName,
  defenderName,
  attackerNationId,
  defenderNationId,
  nation1Id,
  attackerData,
  defenderData,
}: DamageTableProps) {
  const tableId = `damage-${attackerName.replace(/\s+/g, '-').toLowerCase()}-vs-${defenderName
    .replace(/\s+/g, '-')
    .toLowerCase()}`;
  const { columnVisibility, setColumnVisibility, density, setDensity } =
    useTablePersistence(tableId, {
      columnVisibility: {},
      columnOrder: [],
      density: 'xs',
    });

  const [attackerBreakdownOpen, setAttackerBreakdownOpen] = useState(false);
  const [defenderBreakdownOpen, setDefenderBreakdownOpen] = useState(false);

  const toggleAttackerBreakdown = useCallback(() => {
    setAttackerBreakdownOpen((o) => !o);
  }, []);
  const toggleDefenderBreakdown = useCallback(() => {
    setDefenderBreakdownOpen((o) => !o);
  }, []);

  const mergedColumnVisibility = useMemo(
    () =>
      mergeDamageColumnVisibility(
        columnVisibility,
        attackerBreakdownOpen,
        defenderBreakdownOpen,
      ),
    [columnVisibility, attackerBreakdownOpen, defenderBreakdownOpen],
  );

  const handleColumnVisibilityChange = useCallback(
    (
      updater:
        | MRT_VisibilityState
        | ((prev: MRT_VisibilityState) => MRT_VisibilityState),
    ) => {
      setColumnVisibility((prevPersisted) => {
        const prevMerged = mergeDamageColumnVisibility(
          prevPersisted,
          attackerBreakdownOpen,
          defenderBreakdownOpen,
        );
        const nextMerged =
          typeof updater === 'function' ? updater(prevMerged) : updater;
        return stripCostBreakdownVisibilityKeys(nextMerged);
      });
    },
    [setColumnVisibility, attackerBreakdownOpen, defenderBreakdownOpen],
  );

  const attackerNationSlot = nationSlotForId(attackerNationId, nation1Id);
  const defenderNationSlot = nationSlotForId(defenderNationId, nation1Id);
  const netHeadTint = headTintForSlot(attackerNationSlot);

  const combinedData = useMemo<CombinedAttackRow[]>(() => {
    const defenderLookup = new Map(defenderData.map((row) => [row.attackType, row]));
    return attackerData.map((attackerRow) => {
      const defenderRow = defenderLookup.get(attackerRow.attackType);
      return {
        attackType: attackerRow.attackType,
        label: attackerRow.label,
        netDamage: attackerRow.netDamage,
        // Attacker costs: what it costs the attacking nation
        attackerCost: attackerRow.damageReceived,       // attacker's own military losses
        attackerGas: attackerRow.gasConsumed,
        attackerMun: attackerRow.munConsumed,
        attackerSteel: attackerRow.steelConsumed,
        attackerAlum: attackerRow.alumConsumed,
        attackerUranium: attackerRow.uraniumConsumed,
        attackerMoney: attackerRow.moneyUsed,
        // Defender costs: what it costs the defending nation (all derived from attacker's data)
        defenderCost: attackerRow.damageDealt,          // military losses the defender suffers
        defenderInfra: attackerRow.infraDestroyed,      // infra value the defender loses
        // Defender's own resource consumption in the battle
        defenderGas: defenderRow?.gasConsumed ?? 0,
        defenderMun: defenderRow?.munConsumed ?? 0,
        defenderSteel: defenderRow?.steelConsumed ?? 0,
        defenderAlum: defenderRow?.alumConsumed ?? 0,
        defenderUranium: defenderRow?.uraniumConsumed ?? 0,
        defenderMoney: defenderRow?.moneyUsed ?? 0,
      };
    });
  }, [attackerData, defenderData]);

  const columns = useMemo<MRT_ColumnDef<CombinedAttackRow>[]>(() => {
    const attackerCluster = getCostClusterTheme(attackerNationSlot);
    /**
     * Attack Type | Net Dealt uses the same recipe as Net Dealt | first cost column:
     * outward colored line + glow on the left column’s right edge; neutral hairline + inset on the right column’s left edge.
     */
    const attackTypeVsNetSeam = {
      borderRight: attackerCluster.interNationBorderRight,
      boxShadow: attackerCluster.interNationRailClose,
    };

    /** Bilateral verticals: mirrors first attacker Cost cell (left) partnering with Net’s right seam. */
    const netDealtColumnSeams = {
      borderLeft: attackerCluster.interNationDividerLeft,
      borderRight: attackerCluster.interNationBorderRight,
      boxShadow: `${attackerCluster.interNationRailInsetLeft}, ${attackerCluster.interNationRailClose}`,
    };

    const attackerLeaves = buildWarPartyBreakdownLeaves(
      'attacker',
      attackerNationSlot,
      attackerName,
      true,
      attackerBreakdownOpen,
    );
    const defenderLeaves = buildWarPartyBreakdownLeaves(
      'defender',
      defenderNationSlot,
      defenderName,
      false,
      defenderBreakdownOpen,
    );

    const costColumns: MRT_ColumnDef<CombinedAttackRow>[] = [
      ...wrapWarPartyBreakdownGroup(
        'attacker',
        attackerNationSlot,
        attackerName,
        true,
        attackerBreakdownOpen,
        toggleAttackerBreakdown,
        attackerLeaves,
      ),
      ...wrapWarPartyBreakdownGroup(
        'defender',
        defenderNationSlot,
        defenderName,
        false,
        defenderBreakdownOpen,
        toggleDefenderBreakdown,
        defenderLeaves,
      ),
    ];

    return [
      {
        accessorKey: 'label',
        header: 'Attack Type',
        Header: () => wrappedHeader('Attack Type'),
        size: 130,
        mantineTableHeadCellProps: {
          style: { ...DAMAGE_HEAD_CELL_PAD, ...attackTypeVsNetSeam },
        },
        mantineTableBodyCellProps: {
          fz: 'sm',
          style: { ...DAMAGE_BODY_CELL_PAD, ...attackTypeVsNetSeam },
        },
      },
      {
        accessorKey: 'netDamage',
        header: 'Net Dealt',
        Header: () => wrappedHeader('Net Dealt'),
        size: 108,
        mantineTableBodyCellProps: {
          fz: 'sm',
          style: {
            ...DAMAGE_BODY_CELL_PAD,
            textAlign: 'right',
            backgroundColor: netHeadTint.backgroundColor,
            ...netDealtColumnSeams,
          },
        },
        mantineTableHeadCellProps: {
          style: { ...DAMAGE_HEAD_CELL_PAD, ...netHeadTint, ...netDealtColumnSeams },
        },
        Cell: ({ cell }) => {
          const v = cell.getValue<number>();
          const color =
            v > 0
              ? 'var(--mantine-color-green-4)'
              : v < 0
                ? 'var(--mantine-color-red-5)'
                : 'var(--mantine-color-dimmed)';
          return (
            <span style={{ color, fontVariantNumeric: 'tabular-nums' }}>
              ${v.toLocaleString()}
            </span>
          );
        },
      },
      ...costColumns,
    ];
  }, [
    attackerName,
    defenderName,
    attackerNationSlot,
    defenderNationSlot,
    netHeadTint,
    attackerBreakdownOpen,
    defenderBreakdownOpen,
    toggleAttackerBreakdown,
    toggleDefenderBreakdown,
  ]);

  const table = useMantineReactTable({
    /* MRT defaults maxSize: 1000 — sizes above that are silently clamped and skew proportions. */
    defaultColumn: { maxSize: Number.MAX_SAFE_INTEGER },
    columns,
    data: combinedData,
    enableColumnPinning: true,
    enablePagination: false,
    enableSorting: true,
    enableColumnFilters: false,
    enableTopToolbar: false,
    enableBottomToolbar: false,
    state: {
      columnVisibility: mergedColumnVisibility,
      density,
    },
    initialState: {
      columnPinning: { left: ['label'] },
    },
    onColumnVisibilityChange: handleColumnVisibilityChange,
    onDensityChange: setDensity,
    mantinePaperProps: {
      shadow: 'none',
      withBorder: false,
    },
    mantineTableProps: {
      className: 'damage-mrt-table',
      striped: false,
      highlightOnHover: true,
      verticalSpacing: 0,
      /*
       * `fixed` + width 100% forces all columns to share one viewport — raising one `size`
       * shrinks neighbors. `auto` + max-content keeps each column near its `size` hint;
       * overflow scrolls (MRT container is overflow:auto). Slight Cost/Sum width drift vs
       * before is possible if content differs.
       */
      style: {
        tableLayout: 'auto',
        width: 'max-content',
        minWidth: '100%',
      },
    },
  });

  return <MantineReactTable table={table} />;
}
