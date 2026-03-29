/**
 * Damage Table Component
 *
 * Table showing detailed attack statistics.
 */

import { useMemo } from 'react';
import {
  MantineReactTable,
  useMantineReactTable,
  type MRT_ColumnDef,
} from 'mantine-react-table';
import { Group, Text } from '@mantine/core';

import type { AttackStats, ResourceType } from '@/types';
import { useTablePersistence } from '@/hooks';
import { ResourceIcon } from '@/components/common';

interface DamageTableProps {
  attackerName: string;
  defenderName: string;
  attackerData: AttackStats[];
  defenderData: AttackStats[];
}

interface CombinedAttackRow {
  attackType: string;
  label: string;
  attackerNetDamage: number;
  defenderNetDamage: number;
  attackerDamageDealt: number;
  defenderDamageDealt: number;
  attackerDamageReceived: number;
  defenderDamageReceived: number;
  attackerGasConsumed: number;
  defenderGasConsumed: number;
  attackerMunConsumed: number;
  defenderMunConsumed: number;
  attackerSteelConsumed: number;
  defenderSteelConsumed: number;
  attackerAlumConsumed: number;
  defenderAlumConsumed: number;
  attackerUraniumConsumed: number;
  defenderUraniumConsumed: number;
  attackerMoneyUsed: number;
  defenderMoneyUsed: number;
  attackerInfraDestroyed: number;
  defenderInfraDestroyed: number;
}

export function DamageTable({
  attackerName,
  defenderName,
  attackerData,
  defenderData,
}: DamageTableProps) {
  const tableId = `damage-${attackerName.replace(/\s+/g, '-').toLowerCase()}-vs-${defenderName
    .replace(/\s+/g, '-')
    .toLowerCase()}`;
  const { columnVisibility, setColumnVisibility, density, setDensity } =
    useTablePersistence(tableId);

  const combinedData = useMemo<CombinedAttackRow[]>(() => {
    const defenderLookup = new Map(defenderData.map((row) => [row.attackType, row]));
    return attackerData.map((attackerRow) => {
      const defenderRow = defenderLookup.get(attackerRow.attackType);
      return {
        attackType: attackerRow.attackType,
        label: attackerRow.label,
        attackerNetDamage: attackerRow.netDamage,
        defenderNetDamage: defenderRow?.netDamage ?? 0,
        attackerDamageDealt: attackerRow.damageDealt,
        defenderDamageDealt: defenderRow?.damageDealt ?? 0,
        attackerDamageReceived: attackerRow.damageReceived,
        defenderDamageReceived: defenderRow?.damageReceived ?? 0,
        attackerGasConsumed: attackerRow.gasConsumed,
        defenderGasConsumed: defenderRow?.gasConsumed ?? 0,
        attackerMunConsumed: attackerRow.munConsumed,
        defenderMunConsumed: defenderRow?.munConsumed ?? 0,
        attackerSteelConsumed: attackerRow.steelConsumed,
        defenderSteelConsumed: defenderRow?.steelConsumed ?? 0,
        attackerAlumConsumed: attackerRow.alumConsumed,
        defenderAlumConsumed: defenderRow?.alumConsumed ?? 0,
        attackerUraniumConsumed: attackerRow.uraniumConsumed,
        defenderUraniumConsumed: defenderRow?.uraniumConsumed ?? 0,
        attackerMoneyUsed: attackerRow.moneyUsed,
        defenderMoneyUsed: defenderRow?.moneyUsed ?? 0,
        attackerInfraDestroyed: attackerRow.infraDestroyed,
        defenderInfraDestroyed: defenderRow?.infraDestroyed ?? 0,
      };
    });
  }, [attackerData, defenderData]);

  const attackerCellStyle = { backgroundColor: 'rgba(34, 139, 230, 0.12)' };
  const defenderCellStyle = { backgroundColor: 'rgba(250, 82, 82, 0.12)' };

  const renderResourceHeader = (label: string, resource: ResourceType, suffix: string) => (
    <Group gap={6} wrap="nowrap" style={{ whiteSpace: 'nowrap' }}>
      <Text size="xs" fw={600}>
        {label}
      </Text>
      <ResourceIcon resource={resource} showValue={false} size={16} />
      <Text size="xs" fw={600}>
        {suffix}
      </Text>
    </Group>
  );

  const columns = useMemo<MRT_ColumnDef<CombinedAttackRow>[]>(
    () => [
      {
        accessorKey: 'label',
        header: 'Attack Type',
        Header: () => (
          <Text size="xs" fw={600} component="div">
            Attack Type
          </Text>
        ),
        size: 130,
      },
      {
        accessorKey: 'attackerNetDamage',
        header: 'Attacker net dealt',
        Header: () => (
          <Text size="xs" fw={600} component="div">
            {attackerName} Net Dealt
          </Text>
        ),
        size: 120,
        mantineTableBodyCellProps: ({ cell }) => ({
          style: {
            textAlign: 'right',
            backgroundColor: attackerCellStyle.backgroundColor,
            color:
              cell.getValue<number>() > 0
                ? 'var(--mantine-color-green-6)'
                : cell.getValue<number>() < 0
                ? 'var(--mantine-color-red-6)'
                : undefined,
          },
        }),
        mantineTableHeadCellProps: {
          style: attackerCellStyle,
        },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'defenderNetDamage',
        header: 'Defender net dealt',
        Header: () => (
          <Text size="xs" fw={600} component="div">
            {defenderName} Net Dealt
          </Text>
        ),
        size: 120,
        mantineTableBodyCellProps: ({ cell }) => ({
          style: {
            textAlign: 'right',
            backgroundColor: defenderCellStyle.backgroundColor,
            color:
              cell.getValue<number>() > 0
                ? 'var(--mantine-color-green-6)'
                : cell.getValue<number>() < 0
                ? 'var(--mantine-color-red-6)'
                : undefined,
          },
        }),
        mantineTableHeadCellProps: {
          style: defenderCellStyle,
        },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'attackerDamageDealt',
        header: 'Attacker total dealt',
        Header: () => (
          <Text size="xs" fw={600} component="div">
            {attackerName} Total Dealt
          </Text>
        ),
        size: 140,
        mantineTableBodyCellProps: () => ({
          style: {
            textAlign: 'right',
            ...attackerCellStyle,
          },
        }),
        mantineTableHeadCellProps: { style: attackerCellStyle },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'defenderDamageDealt',
        header: 'Defender total dealt',
        Header: () => (
          <Text size="xs" fw={600} component="div">
            {defenderName} Total Dealt
          </Text>
        ),
        size: 140,
        mantineTableBodyCellProps: () => ({
          style: {
            textAlign: 'right',
            ...defenderCellStyle,
          },
        }),
        mantineTableHeadCellProps: { style: defenderCellStyle },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'attackerDamageReceived',
        header: 'Attacker total received',
        Header: () => (
          <Text size="xs" fw={600} component="div">
            {attackerName} Total Received
          </Text>
        ),
        size: 130,
        mantineTableBodyCellProps: () => ({
          style: {
            textAlign: 'right',
            ...attackerCellStyle,
          },
        }),
        mantineTableHeadCellProps: { style: attackerCellStyle },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'defenderDamageReceived',
        header: 'Defender total received',
        Header: () => (
          <Text size="xs" fw={600} component="div">
            {defenderName} Total Received
          </Text>
        ),
        size: 130,
        mantineTableBodyCellProps: () => ({
          style: {
            textAlign: 'right',
            ...defenderCellStyle,
          },
        }),
        mantineTableHeadCellProps: { style: defenderCellStyle },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'attackerGasConsumed',
        header: 'Attacker gas consumed',
        Header: () => renderResourceHeader(attackerName, 'gasoline', 'Consumed'),
        size: 80,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...attackerCellStyle } },
        mantineTableHeadCellProps: { style: { ...attackerCellStyle, whiteSpace: 'nowrap' } },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'defenderGasConsumed',
        header: 'Defender gas consumed',
        Header: () => renderResourceHeader(defenderName, 'gasoline', 'Consumed'),
        size: 80,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...defenderCellStyle } },
        mantineTableHeadCellProps: { style: { ...defenderCellStyle, whiteSpace: 'nowrap' } },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'attackerMunConsumed',
        header: 'Attacker munitions consumed',
        Header: () => renderResourceHeader(attackerName, 'munitions', 'Consumed'),
        size: 80,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...attackerCellStyle } },
        mantineTableHeadCellProps: { style: { ...attackerCellStyle, whiteSpace: 'nowrap' } },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'defenderMunConsumed',
        header: 'Defender munitions consumed',
        Header: () => renderResourceHeader(defenderName, 'munitions', 'Consumed'),
        size: 80,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...defenderCellStyle } },
        mantineTableHeadCellProps: { style: { ...defenderCellStyle, whiteSpace: 'nowrap' } },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'attackerSteelConsumed',
        header: 'Attacker steel consumed',
        Header: () => renderResourceHeader(attackerName, 'steel', 'Consumed'),
        size: 90,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...attackerCellStyle } },
        mantineTableHeadCellProps: { style: { ...attackerCellStyle, whiteSpace: 'nowrap' } },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'defenderSteelConsumed',
        header: 'Defender steel consumed',
        Header: () => renderResourceHeader(defenderName, 'steel', 'Consumed'),
        size: 90,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...defenderCellStyle } },
        mantineTableHeadCellProps: { style: { ...defenderCellStyle, whiteSpace: 'nowrap' } },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'attackerAlumConsumed',
        header: 'Attacker aluminum consumed',
        Header: () => renderResourceHeader(attackerName, 'aluminum', 'Consumed'),
        size: 80,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...attackerCellStyle } },
        mantineTableHeadCellProps: { style: { ...attackerCellStyle, whiteSpace: 'nowrap' } },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'defenderAlumConsumed',
        header: 'Defender aluminum consumed',
        Header: () => renderResourceHeader(defenderName, 'aluminum', 'Consumed'),
        size: 80,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...defenderCellStyle } },
        mantineTableHeadCellProps: { style: { ...defenderCellStyle, whiteSpace: 'nowrap' } },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'attackerUraniumConsumed',
        header: 'Attacker uranium consumed',
        Header: () => renderResourceHeader(attackerName, 'uranium', 'Consumed'),
        size: 110,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...attackerCellStyle } },
        mantineTableHeadCellProps: { style: { ...attackerCellStyle, whiteSpace: 'nowrap' } },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'defenderUraniumConsumed',
        header: 'Defender uranium consumed',
        Header: () => renderResourceHeader(defenderName, 'uranium', 'Consumed'),
        size: 110,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...defenderCellStyle } },
        mantineTableHeadCellProps: { style: { ...defenderCellStyle, whiteSpace: 'nowrap' } },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'attackerMoneyUsed',
        header: 'Attacker money consumed',
        Header: () => renderResourceHeader(attackerName, 'money', 'Consumed'),
        size: 100,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...attackerCellStyle } },
        mantineTableHeadCellProps: { style: { ...attackerCellStyle, whiteSpace: 'nowrap' } },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'defenderMoneyUsed',
        header: 'Defender money consumed',
        Header: () => renderResourceHeader(defenderName, 'money', 'Consumed'),
        size: 100,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...defenderCellStyle } },
        mantineTableHeadCellProps: { style: { ...defenderCellStyle, whiteSpace: 'nowrap' } },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'attackerInfraDestroyed',
        header: 'Attacker infra damage dealt',
        Header: () => (
          <Text size="xs" fw={600} component="div">
            {attackerName} Infra Damage Dealt
          </Text>
        ),
        size: 120,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...attackerCellStyle } },
        mantineTableHeadCellProps: { style: { ...attackerCellStyle, whiteSpace: 'nowrap' } },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'defenderInfraDestroyed',
        header: 'Defender infra damage dealt',
        Header: () => (
          <Text size="xs" fw={600} component="div">
            {defenderName} Infra Damage Dealt
          </Text>
        ),
        size: 120,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...defenderCellStyle } },
        mantineTableHeadCellProps: { style: { ...defenderCellStyle, whiteSpace: 'nowrap' } },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
    ],
    [attackerName, defenderName]
  );

  const table = useMantineReactTable({
    columns,
    data: combinedData,
    enableColumnPinning: true,
    enablePagination: false,
    enableSorting: true,
    enableColumnFilters: false,
    enableTopToolbar: false,
    enableBottomToolbar: false,
    state: {
      columnVisibility,
      density,
    },
    initialState: {
      columnPinning: { left: ['label'] },
    },
    onColumnVisibilityChange: setColumnVisibility,
    onDensityChange: setDensity,
    mantinePaperProps: {
      shadow: 'none',
      withBorder: false,
    },
    mantineTableProps: {
      striped: true,
      highlightOnHover: true,
      style: { tableLayout: 'auto' },
    },
    mantineTableHeadCellProps: {
      style: { whiteSpace: 'normal', lineHeight: 1.2 },
    },
  });

  return (
    <MantineReactTable table={table} />
  );
}
