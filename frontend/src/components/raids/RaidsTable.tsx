/**
 * Raids Table Component
 *
 * Displays raid targets using Mantine React Table with:
 * - Client-side filtering, sorting, pagination
 * - Deep linking via URL params
 * - Persistent column preferences
 * - Beige reminder functionality
 */

import { useMemo, useCallback } from 'react';
import {
  MantineReactTable,
  useMantineReactTable,
  type MRT_ColumnDef,
  type MRT_Row,
} from 'mantine-react-table';
import {
  ActionIcon,
  Anchor,
  Badge,
  Group,
  Text,
  Tooltip,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { IconBell, IconBellOff, IconExternalLink } from '@tabler/icons-react';

import type { RaidTarget } from '@/types';
import { addReminder, removeReminder } from '@/api';
import { useTablePersistence } from '@/hooks';

interface RaidsTableProps {
  data: RaidTarget[];
  token: string;
  showBeige: boolean;
  initialFilters?: { id: string; value: unknown }[];
  initialSorting?: { id: string; desc: boolean }[];
}

export function RaidsTable({
  data,
  token,
  showBeige,
  initialFilters = [],
  initialSorting = [],
}: RaidsTableProps) {
  const queryClient = useQueryClient();

  // Persist table preferences
  const {
    columnVisibility,
    columnOrder,
    density,
    setColumnVisibility,
    setColumnOrder,
    setDensity,
  } = useTablePersistence('raids');

  // Add reminder mutation
  const addReminderMutation = useMutation({
    mutationFn: (nationId: number) => addReminder(token, { nationId }),
    onSuccess: (_, nationId) => {
      notifications.show({
        title: 'Reminder Set',
        message: `You will be notified when nation ${nationId} exits beige.`,
        color: 'green',
      });
      queryClient.invalidateQueries({ queryKey: ['raids'] });
    },
    onError: (error: Error) => {
      notifications.show({
        title: 'Error',
        message: error.message || 'Failed to set reminder',
        color: 'red',
      });
    },
  });

  // Remove reminder mutation
  const removeReminderMutation = useMutation({
    mutationFn: (nationId: number) => removeReminder(token, nationId),
    onSuccess: (_, nationId) => {
      notifications.show({
        title: 'Reminder Removed',
        message: `Reminder for nation ${nationId} has been removed.`,
        color: 'blue',
      });
      queryClient.invalidateQueries({ queryKey: ['raids'] });
    },
    onError: (error: Error) => {
      notifications.show({
        title: 'Error',
        message: error.message || 'Failed to remove reminder',
        color: 'red',
      });
    },
  });

  // Handle reminder toggle
  const handleReminderToggle = useCallback(
    (row: MRT_Row<RaidTarget>) => {
      const nation = row.original;
      if (nation.hasReminderActive) {
        removeReminderMutation.mutate(nation.id);
      } else {
        addReminderMutation.mutate(nation.id);
      }
    },
    [addReminderMutation, removeReminderMutation]
  );

  // Define columns
  const columns = useMemo<MRT_ColumnDef<RaidTarget>[]>(
    () => [
      {
        accessorKey: 'id',
        header: 'Nation ID',
        size: 100,
      },
      {
        accessorKey: 'nationName',
        header: 'Nation Name',
        size: 150,
        Cell: ({ row }) => (
          <Anchor
            href={`https://politicsandwar.com/nation/id=${row.original.id}`}
            target="_blank"
            size="sm"
          >
            {row.original.nationName}
          </Anchor>
        ),
      },
      {
        accessorKey: 'leaderName',
        header: 'Leader',
        size: 120,
      },
      {
        accessorKey: 'allianceName',
        header: 'Alliance',
        size: 150,
        Cell: ({ row }) =>
          row.original.allianceId !== '0' ? (
            <Anchor
              href={`https://politicsandwar.com/alliance/id=${row.original.allianceId}`}
              target="_blank"
              size="sm"
            >
              {row.original.allianceName}
            </Anchor>
          ) : (
            <Text size="sm" c="dimmed">
              None
            </Text>
          ),
      },
      {
        accessorKey: 'alliancePosition',
        header: 'Position',
        size: 100,
        Cell: ({ cell }) => {
          const value = cell.getValue<string>();
          return value === 'NOALLIANCE' ? 'None' : value.toLowerCase();
        },
      },
      {
        accessorKey: 'numCities',
        header: 'Cities',
        size: 80,
        filterVariant: 'range-slider',
      },
      {
        accessorKey: 'color',
        header: 'Color',
        size: 100,
        Cell: ({ cell }) => (
          <Badge variant="light" color={getColorBadge(cell.getValue<string>())}>
            {cell.getValue<string>()}
          </Badge>
        ),
      },
      ...(showBeige
        ? [
            {
              accessorKey: 'beigeTurns',
              header: 'Beige Turns',
              size: 100,
            } as MRT_ColumnDef<RaidTarget>,
            {
              id: 'reminder',
              header: 'Reminder',
              size: 100,
              enableSorting: false,
              enableColumnFilter: false,
              Cell: ({ row }: { row: MRT_Row<RaidTarget> }) => {
                const nation = row.original;
                if (nation.beigeTurns <= 0) {
                  return (
                    <Text size="sm" c="dimmed">
                      Not beige
                    </Text>
                  );
                }
                return (
                  <Tooltip
                    label={
                      nation.hasReminderActive
                        ? 'Remove reminder'
                        : 'Set reminder'
                    }
                  >
                    <ActionIcon
                      variant={nation.hasReminderActive ? 'filled' : 'light'}
                      color={nation.hasReminderActive ? 'green' : 'gray'}
                      onClick={() => handleReminderToggle(row)}
                      loading={
                        addReminderMutation.isPending ||
                        removeReminderMutation.isPending
                      }
                    >
                      {nation.hasReminderActive ? (
                        <IconBell size={16} />
                      ) : (
                        <IconBellOff size={16} />
                      )}
                    </ActionIcon>
                  </Tooltip>
                );
              },
            } as MRT_ColumnDef<RaidTarget>,
          ]
        : []),
      {
        accessorKey: 'nationLoot',
        header: 'Beige Loot',
        size: 120,
        mantineTableBodyCellProps: { align: 'right' },
      },
      {
        accessorKey: 'daysInactive',
        header: 'Days Inactive',
        size: 100,
        mantineTableBodyCellProps: { align: 'right' },
      },
      {
        accessorKey: 'monetaryNetIncome',
        header: 'Net Income',
        size: 120,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'netCashIncome',
        header: 'Cash Income',
        size: 120,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
      },
      {
        accessorKey: 'taxable',
        header: 'Taxable',
        size: 80,
        Cell: ({ cell }) => (cell.getValue<boolean>() ? 'Yes' : 'No'),
      },
      {
        accessorKey: 'treasures',
        header: 'Treasures',
        size: 80,
        mantineTableBodyCellProps: { align: 'right' },
      },
      {
        accessorKey: 'defSlots',
        header: 'Def Slots',
        size: 80,
        Cell: ({ cell }) => `${cell.getValue<number>()}/3`,
      },
      {
        accessorKey: 'timeSinceWar',
        header: 'Days Since War',
        size: 100,
      },
      {
        accessorKey: 'soldiers',
        header: 'Soldiers',
        size: 100,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'tanks',
        header: 'Tanks',
        size: 80,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
      },
      {
        accessorKey: 'aircraft',
        header: 'Aircraft',
        size: 80,
        mantineTableBodyCellProps: { align: 'right' },
      },
      {
        accessorKey: 'ships',
        header: 'Ships',
        size: 80,
        mantineTableBodyCellProps: { align: 'right' },
      },
      {
        accessorKey: 'missiles',
        header: 'Missiles',
        size: 80,
        mantineTableBodyCellProps: { align: 'right' },
      },
      {
        accessorKey: 'nukes',
        header: 'Nukes',
        size: 80,
        mantineTableBodyCellProps: { align: 'right' },
      },
      {
        accessorKey: 'groundWin',
        header: 'Ground Win%',
        size: 100,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `${cell.getValue<number>()}%`,
      },
      {
        accessorKey: 'airWin',
        header: 'Air Win%',
        size: 100,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `${cell.getValue<number>()}%`,
      },
      {
        accessorKey: 'navalWin',
        header: 'Naval Win%',
        size: 100,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `${cell.getValue<number>()}%`,
      },
      {
        accessorKey: 'totalWin',
        header: 'Total Win%',
        size: 100,
        mantineTableBodyCellProps: { align: 'right' },
      },
      {
        id: 'actions',
        header: 'Actions',
        size: 80,
        enableSorting: false,
        enableColumnFilter: false,
        Cell: ({ row }) => (
          <Group gap="xs">
            <Tooltip label="Declare War">
              <ActionIcon
                variant="light"
                color="red"
                component="a"
                href={`https://politicsandwar.com/nation/war/declare/id=${row.original.id}`}
                target="_blank"
              >
                <IconExternalLink size={16} />
              </ActionIcon>
            </Tooltip>
          </Group>
        ),
      },
    ],
    [showBeige, handleReminderToggle, addReminderMutation.isPending, removeReminderMutation.isPending]
  );

  const table = useMantineReactTable({
    columns,
    data,
    enableColumnOrdering: true,
    enableColumnResizing: false,
    enablePagination: true,
    enableStickyHeader: true,
    enableRowVirtualization: data.length > 100,
    initialState: {
      columnFilters: initialFilters,
      sorting: initialSorting,
      pagination: { pageSize: 50, pageIndex: 0 },
    },
    state: {
      columnVisibility,
      columnOrder,
      density,
    },
    onColumnVisibilityChange: setColumnVisibility,
    onColumnOrderChange: setColumnOrder,
    onDensityChange: setDensity,
    mantineTableContainerProps: {
      style: {
        maxHeight: '600px',
      },
    },
    mantineTableProps: {
      className: 'raids-table',
    },
    mantineTableHeadCellProps: {
      style: {
        padding: '12px 10px',
        minHeight: '64px',
        textAlign: 'center',
        verticalAlign: 'top',
        whiteSpace: 'normal',
        wordBreak: 'break-word',
        lineHeight: 1.3,
      },
    },
    mantinePaperProps: {
      shadow: 'sm',
      radius: 'md',
      withBorder: true,
    },
  });

  return <MantineReactTable table={table} />;
}

// Helper to get badge color based on nation color
function getColorBadge(color: string): string {
  const colorMap: Record<string, string> = {
    aqua: 'cyan',
    black: 'dark',
    blue: 'blue',
    brown: 'orange',
    green: 'green',
    lime: 'lime',
    maroon: 'red',
    olive: 'yellow',
    orange: 'orange',
    pink: 'pink',
    purple: 'grape',
    red: 'red',
    white: 'gray',
    yellow: 'yellow',
    beige: 'yellow',
    gray: 'gray',
  };
  return colorMap[color.toLowerCase()] || 'gray';
}
