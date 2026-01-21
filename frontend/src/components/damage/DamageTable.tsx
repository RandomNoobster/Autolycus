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
import { Paper, Title } from '@mantine/core';

import type { AttackStats } from '@/types';
import { useTablePersistence } from '@/hooks';

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
  attackerFoodConsumed: number;
  defenderFoodConsumed: number;
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
        attackerFoodConsumed: attackerRow.foodConsumed,
        defenderFoodConsumed: defenderRow?.foodConsumed ?? 0,
        attackerMoneyUsed: attackerRow.moneyUsed,
        defenderMoneyUsed: defenderRow?.moneyUsed ?? 0,
        attackerInfraDestroyed: attackerRow.infraDestroyed,
        defenderInfraDestroyed: defenderRow?.infraDestroyed ?? 0,
      };
    });
  }, [attackerData, defenderData]);

  const attackerCellStyle = { backgroundColor: 'rgba(34, 139, 230, 0.12)' };
  const defenderCellStyle = { backgroundColor: 'rgba(250, 82, 82, 0.12)' };

  const getValueColor = (value: number, invert = false) => {
    if (value === 0) return undefined;
    if (invert) {
      return value < 0 ? 'var(--mantine-color-green-6)' : 'var(--mantine-color-red-6)';
    }
    return value > 0 ? 'var(--mantine-color-green-6)' : 'var(--mantine-color-red-6)';
  };

  const columns = useMemo<MRT_ColumnDef<CombinedAttackRow>[]>(
    () => [
      {
        accessorKey: 'label',
        header: 'Attack Type',
        size: 130,
      },
      {
        accessorKey: 'attackerNetDamage',
        header: `${attackerName} Net`,
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
        header: `${defenderName} Net`,
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
        header: `${attackerName} Dealt`,
        size: 120,
        mantineTableBodyCellProps: ({ cell }) => ({
          style: {
            textAlign: 'right',
            ...attackerCellStyle,
            color: getValueColor(cell.getValue<number>()),
          },
        }),
        mantineTableHeadCellProps: { style: attackerCellStyle },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'defenderDamageDealt',
        header: `${defenderName} Dealt`,
        size: 120,
        mantineTableBodyCellProps: ({ cell }) => ({
          style: {
            textAlign: 'right',
            ...defenderCellStyle,
            color: getValueColor(cell.getValue<number>()),
          },
        }),
        mantineTableHeadCellProps: { style: defenderCellStyle },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'attackerDamageReceived',
        header: `${attackerName} Received`,
        size: 130,
        mantineTableBodyCellProps: ({ cell }) => ({
          style: {
            textAlign: 'right',
            ...attackerCellStyle,
            color: getValueColor(cell.getValue<number>(), true),
          },
        }),
        mantineTableHeadCellProps: { style: attackerCellStyle },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'defenderDamageReceived',
        header: `${defenderName} Received`,
        size: 130,
        mantineTableBodyCellProps: ({ cell }) => ({
          style: {
            textAlign: 'right',
            ...defenderCellStyle,
            color: getValueColor(cell.getValue<number>(), true),
          },
        }),
        mantineTableHeadCellProps: { style: defenderCellStyle },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'attackerGasConsumed',
        header: `${attackerName} Gas`,
        size: 80,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...attackerCellStyle } },
        mantineTableHeadCellProps: { style: attackerCellStyle },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'defenderGasConsumed',
        header: `${defenderName} Gas`,
        size: 80,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...defenderCellStyle } },
        mantineTableHeadCellProps: { style: defenderCellStyle },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'attackerMunConsumed',
        header: `${attackerName} Mun`,
        size: 80,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...attackerCellStyle } },
        mantineTableHeadCellProps: { style: attackerCellStyle },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'defenderMunConsumed',
        header: `${defenderName} Mun`,
        size: 80,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...defenderCellStyle } },
        mantineTableHeadCellProps: { style: defenderCellStyle },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'attackerSteelConsumed',
        header: `${attackerName} Steel`,
        size: 90,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...attackerCellStyle } },
        mantineTableHeadCellProps: { style: attackerCellStyle },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'defenderSteelConsumed',
        header: `${defenderName} Steel`,
        size: 90,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...defenderCellStyle } },
        mantineTableHeadCellProps: { style: defenderCellStyle },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'attackerAlumConsumed',
        header: `${attackerName} Alum`,
        size: 80,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...attackerCellStyle } },
        mantineTableHeadCellProps: { style: attackerCellStyle },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'defenderAlumConsumed',
        header: `${defenderName} Alum`,
        size: 80,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...defenderCellStyle } },
        mantineTableHeadCellProps: { style: defenderCellStyle },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'attackerUraniumConsumed',
        header: `${attackerName} Uranium`,
        size: 110,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...attackerCellStyle } },
        mantineTableHeadCellProps: { style: attackerCellStyle },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'defenderUraniumConsumed',
        header: `${defenderName} Uranium`,
        size: 110,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...defenderCellStyle } },
        mantineTableHeadCellProps: { style: defenderCellStyle },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'attackerFoodConsumed',
        header: `${attackerName} Food`,
        size: 90,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...attackerCellStyle } },
        mantineTableHeadCellProps: { style: attackerCellStyle },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'defenderFoodConsumed',
        header: `${defenderName} Food`,
        size: 90,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...defenderCellStyle } },
        mantineTableHeadCellProps: { style: defenderCellStyle },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'attackerMoneyUsed',
        header: `${attackerName} Money`,
        size: 100,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...attackerCellStyle } },
        mantineTableHeadCellProps: { style: attackerCellStyle },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'defenderMoneyUsed',
        header: `${defenderName} Money`,
        size: 100,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...defenderCellStyle } },
        mantineTableHeadCellProps: { style: defenderCellStyle },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'attackerInfraDestroyed',
        header: `${attackerName} Infra`,
        size: 120,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...attackerCellStyle } },
        mantineTableHeadCellProps: { style: attackerCellStyle },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'defenderInfraDestroyed',
        header: `${defenderName} Infra`,
        size: 120,
        mantineTableBodyCellProps: { style: { textAlign: 'right', ...defenderCellStyle } },
        mantineTableHeadCellProps: { style: defenderCellStyle },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
    ],
    [attackerName, defenderName]
  );

  const table = useMantineReactTable({
    columns,
    data: combinedData,
    enablePagination: false,
    enableSorting: true,
    enableColumnFilters: false,
    enableTopToolbar: false,
    enableBottomToolbar: false,
    state: {
      columnVisibility,
      density,
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
    },
  });

  return (
    <Paper shadow="sm" p="lg" radius="md" withBorder>
      <Title order={4} mb="md">
        {attackerName} vs {defenderName} (Combined)
      </Title>
      <MantineReactTable table={table} />
    </Paper>
  );
}
