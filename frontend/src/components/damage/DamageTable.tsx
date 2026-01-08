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
import { Paper, Title, Tabs } from '@mantine/core';

import type { AttackStats } from '@/types';
import { useTablePersistence } from '@/hooks';

interface DamageTableProps {
  nationName: string;
  role: 'attacker' | 'defender';
  perResistance: AttackStats[];
  perMap: AttackStats[];
  totalStats: AttackStats[];
}

export function DamageTable({
  nationName,
  role,
  perResistance,
  perMap,
  totalStats,
}: DamageTableProps) {
  const tableId = `damage-${nationName.replace(/\s+/g, '-').toLowerCase()}-${role}`;
  const { columnVisibility, setColumnVisibility, density, setDensity } =
    useTablePersistence(tableId);

  const columns = useMemo<MRT_ColumnDef<AttackStats>[]>(
    () => [
      {
        accessorKey: 'label',
        header: 'Attack Type',
        size: 130,
      },
      {
        accessorKey: 'netDamage',
        header: 'Net Damage',
        size: 120,
        mantineTableBodyCellProps: ({ cell }) => ({
          style: {
            textAlign: 'right',
            color:
              cell.getValue<number>() > 0
                ? 'var(--mantine-color-green-6)'
                : cell.getValue<number>() < 0
                ? 'var(--mantine-color-red-6)'
                : undefined,
          },
        }),
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'damageDealt',
        header: 'Damage Dealt',
        size: 120,
        mantineTableBodyCellProps: { style: { textAlign: 'right' } },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'damageReceived',
        header: 'Damage Received',
        size: 130,
        mantineTableBodyCellProps: { style: { textAlign: 'right' } },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'gasConsumed',
        header: 'Gas',
        size: 80,
        mantineTableBodyCellProps: { style: { textAlign: 'right' } },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'munConsumed',
        header: 'Mun',
        size: 80,
        mantineTableBodyCellProps: { style: { textAlign: 'right' } },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'steelConsumed',
        header: 'Steel',
        size: 80,
        mantineTableBodyCellProps: { style: { textAlign: 'right' } },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'alumConsumed',
        header: 'Alum',
        size: 80,
        mantineTableBodyCellProps: { style: { textAlign: 'right' } },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'moneyUsed',
        header: 'Money',
        size: 100,
        mantineTableBodyCellProps: { style: { textAlign: 'right' } },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'infraDestroyed',
        header: 'Infra Destroyed',
        size: 120,
        mantineTableBodyCellProps: { style: { textAlign: 'right' } },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
    ],
    []
  );

  const table = useMantineReactTable({
    columns,
    data: perResistance, // Default to per-resistance view
    enablePagination: false,
    enableSorting: true,
    enableColumnFilters: false,
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
  });

  // We'll use tabs to switch between the three views
  return (
    <Paper shadow="sm" p="lg" radius="md" withBorder>
      <Title order={4} mb="md">
        {nationName} ({role === 'attacker' ? 'Attacker' : 'Defender'}) Stats
      </Title>
      
      <Tabs defaultValue="resistance">
        <Tabs.List mb="md">
          <Tabs.Tab value="resistance">Per Resistance (Winning)</Tabs.Tab>
          <Tabs.Tab value="map">Per MAP (Losing)</Tabs.Tab>
          <Tabs.Tab value="total">Total (Reference)</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="resistance">
          <StatsTable data={perResistance} columns={columns} tableId={`${tableId}-res`} />
        </Tabs.Panel>

        <Tabs.Panel value="map">
          <StatsTable data={perMap} columns={columns} tableId={`${tableId}-map`} />
        </Tabs.Panel>

        <Tabs.Panel value="total">
          <StatsTable data={totalStats} columns={columns} tableId={`${tableId}-total`} />
        </Tabs.Panel>
      </Tabs>
    </Paper>
  );
}

interface StatsTableProps {
  data: AttackStats[];
  columns: MRT_ColumnDef<AttackStats>[];
  tableId: string;
}

function StatsTable({ data, columns, tableId }: StatsTableProps) {
  const { columnVisibility, setColumnVisibility, density, setDensity } =
    useTablePersistence(tableId);

  const table = useMantineReactTable({
    columns,
    data,
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

  return <MantineReactTable table={table} />;
}
