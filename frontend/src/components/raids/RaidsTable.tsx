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
  Box,
  Alert,
  Stack,
  NumberInput,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { IconBell, IconBellOff, IconExternalLink, IconInfoCircle } from '@tabler/icons-react';

import type { RaidTarget } from '@/types';
import { addReminder, removeReminder } from '@/api';
import { useTablePersistence } from '@/hooks';

// --- HELPER FUNCTIONS FOR FILTERING ---

// Parse numeric values that might contain $, %, +, or commas
const parseNumericValue = (value: unknown): number => {
  if (typeof value === 'number') return value;
  if (typeof value === 'string') {
    const cleaned = value.replace(/[$%+,]/g, '');
    const parsed = parseFloat(cleaned);
    return isNaN(parsed) ? 0 : parsed;
  }
  return 0;
};

// Custom filter: min only
const minOnlyFilter = (row: any, id: string, filterValue: any) => {
  if (filterValue === undefined || filterValue === null || filterValue === '') return true;
  const cellValue = parseNumericValue(row.getValue(id));
  const minValue = parseNumericValue(filterValue);
  return cellValue >= minValue;
};

// Custom filter: max only
const maxOnlyFilter = (row: any, id: string, filterValue: any) => {
  if (filterValue === undefined || filterValue === null || filterValue === '') return true;
  const cellValue = parseNumericValue(row.getValue(id));
  const maxValue = parseNumericValue(filterValue);
  return cellValue <= maxValue;
};

// Custom filter: range with min/max
const rangeFilter = (row: any, id: string, filterValue: any) => {
  if (!filterValue || (!filterValue.min && !filterValue.max)) return true;
  const cellValue = parseNumericValue(row.getValue(id));
  const min = filterValue.min !== undefined ? parseNumericValue(filterValue.min) : -Infinity;
  const max = filterValue.max !== undefined ? parseNumericValue(filterValue.max) : Infinity;
  return cellValue >= min && cellValue <= max;
};

// Custom filter: boolean filter for taxable
const booleanFilter = (row: any, id: string, filterValue: any) => {
  if (filterValue === undefined || filterValue === null || filterValue === '') return true;
  const cellValue = row.getValue(id);
  const filterBool = filterValue === 'true' || filterValue === true;
  return cellValue === filterBool;
};

// --- HELPER FOR WRAPPING HEADERS ---
// This forces the header text to wrap and centers it, overriding default MRT styles.
// We use a Box with fixed line-height to make multiline headers look good.
const wrappedHeader = (text: string) => (
  <Box
    style={{
      whiteSpace: 'normal',
      wordWrap: 'break-word',
      textAlign: 'center',
      lineHeight: '1.1',
      width: '100%',
    }}
  >
    {text}
  </Box>
);

// --- CUSTOM FILTER COMPONENTS ---

// Filter component: Min only (for days inactive, income fields, days since war)
const MinOnlyFilterInput = ({ column }: any) => {
  const filterValue = column.getFilterValue() || '';
  return (
    <NumberInput
      placeholder="Min"
      value={filterValue}
      onChange={(val) => column.setFilterValue(val ?? '')}
      size="xs"
      min={0}
    />
  );
};

// Filter component: Max only (for defensive slots)
const MaxOnlyFilterInput = ({ column }: any) => {
  const filterValue = column.getFilterValue() || '';
  return (
    <NumberInput
      placeholder="Max"
      value={filterValue}
      onChange={(val) => column.setFilterValue(val ?? '')}
      size="xs"
      min={0}
      max={3}
    />
  );
};

// Filter component: Range (for military units and win%)
const RangeFilterInput = ({ column }: any) => {
  const filterValue = column.getFilterValue() || { min: '', max: '' };
  return (
    <Stack gap={4}>
      <NumberInput
        placeholder="Min"
        value={filterValue.min || ''}
        onChange={(val) => column.setFilterValue({ ...filterValue, min: val ?? '' })}
        size="xs"
        min={0}
      />
      <NumberInput
        placeholder="Max"
        value={filterValue.max || ''}
        onChange={(val) => column.setFilterValue({ ...filterValue, max: val ?? '' })}
        size="xs"
        min={0}
      />
    </Stack>
  );
};

interface RaidsTableProps {
  data: RaidTarget[];
  token: string;
  showBeige: boolean;
  discordLinked: boolean;
  initialFilters?: { id: string; value: unknown }[];
  initialSorting?: { id: string; desc: boolean }[];
}

export function RaidsTable({
  data,
  token,
  showBeige,
  discordLinked,
  initialFilters = [],
  initialSorting = [],
}: RaidsTableProps) {
  const queryClient = useQueryClient();

  const {
    columnVisibility,
    columnOrder,
    density,
    setColumnVisibility,
    setColumnOrder,
    setDensity,
  } = useTablePersistence('raids');

  // ... (Keep your mutations same as before) ...
  const addReminderMutation = useMutation({
    mutationFn: (nationId: number) => addReminder(token, { nationId }),
    onSuccess: (_, nationId) => {
      notifications.show({ title: 'Reminder Set', message: `Nation ${nationId}`, color: 'green' });
      queryClient.invalidateQueries({ queryKey: ['raids'] });
    },
    onError: (error: Error) => notifications.show({ title: 'Error', message: error.message, color: 'red' }),
  });

  const removeReminderMutation = useMutation({
    mutationFn: (nationId: number) => removeReminder(token, nationId),
    onSuccess: (_, nationId) => {
      notifications.show({ title: 'Reminder Removed', message: `Nation ${nationId}`, color: 'blue' });
      queryClient.invalidateQueries({ queryKey: ['raids'] });
    },
    onError: (error: Error) => notifications.show({ title: 'Error', message: error.message, color: 'red' }),
  });

  const handleReminderToggle = useCallback((row: MRT_Row<RaidTarget>) => {
    const nation = row.original;
    nation.hasReminderActive ? removeReminderMutation.mutate(nation.id) : addReminderMutation.mutate(nation.id);
  }, [addReminderMutation, removeReminderMutation]);

  // Get unique values for filters
  const uniqueAlliances = useMemo(() => {
    const alliances = new Set(data.map(d => d.allianceName).filter(a => a && a !== 'None'));
    return Array.from(alliances).sort();
  }, [data]);

  const uniquePositions = useMemo(() => {
    const positions = new Set(data.map(d => d.alliancePosition).filter(p => p && p !== 'NOALLIANCE'));
    return Array.from(positions).sort();
  }, [data]);

  const uniqueColors = useMemo(() => {
    const colors = new Set(data.map(d => d.color));
    return Array.from(colors).sort();
  }, [data]);

  const cityRange = useMemo(() => {
    const cities = data.map(d => d.numCities);
    return [Math.min(...cities), Math.max(...cities)];
  }, [data]);

  const columns = useMemo<MRT_ColumnDef<RaidTarget>[]>(
    () => [
      {
        accessorKey: 'id',
        header: 'ID',
        size: 100, 
      },
      {
        accessorKey: 'nationName',
        header: 'Nation Name',
        size: 170,
        Cell: ({ row }) => (
          <Anchor href={`https://politicsandwar.com/nation/id=${row.original.id}`} target="_blank" size="sm">
            {row.original.nationName}
          </Anchor>
        ),
      },
      {
        accessorKey: 'leaderName',
        header: 'Leader',
        size: 130,
      },
      {
        accessorKey: 'allianceName',
        header: 'Alliance',
        size: 140,
        filterVariant: 'multi-select',
        mantineFilterMultiSelectProps: {
          data: uniqueAlliances,
          searchable: true,
          clearable: true,
        },
        Cell: ({ row }) =>
          row.original.allianceId !== '0' ? (
            <Anchor href={`https://politicsandwar.com/alliance/id=${row.original.allianceId}`} target="_blank" size="sm">
              {row.original.allianceName}
            </Anchor>
          ) : (
            <Text size="sm" c="dimmed">None</Text>
          ),
      },
      {
        accessorKey: 'alliancePosition',
        header: 'Position',
        size: 130,
        filterVariant: 'multi-select',
        mantineFilterMultiSelectProps: {
          data: uniquePositions,
          clearable: true,
        },
        Cell: ({ cell }) => {
          const value = cell.getValue<string>();
          return value === 'NOALLIANCE' ? 'None' : value.toLowerCase();
        },
      },
      {
        accessorKey: 'numCities',
        header: 'Cities',
        filterVariant: 'range-slider',
        mantineFilterRangeSliderProps: {
          min: cityRange[0],
          max: cityRange[1],
          step: 1,
        },
        size: 120, // Increased slightly to fit "Cities" + Icon
      },
      {
        accessorKey: 'color',
        header: 'Color',
        size: 120,
        filterVariant: 'multi-select',
        mantineFilterMultiSelectProps: {
          data: uniqueColors,
          clearable: true,
        },
        Cell: ({ cell }) => (
          <Badge variant="light" color={getColorBadge(cell.getValue<string>())}>
            {cell.getValue<string>()}
          </Badge>
        ),
      },
      ...(showBeige && discordLinked
        ? [
            {
              accessorKey: 'beigeTurns',
              header: 'Beige Turns',
              Header: () => wrappedHeader('Beige Turns'), // Use custom wrapper
              size: 120, 
            } as MRT_ColumnDef<RaidTarget>,
            {
              id: 'reminder',
              header: 'Remind', // Shortened text
              size: 70,
              enableSorting: false,
              enableColumnFilter: false,
              Cell: ({ row }: { row: MRT_Row<RaidTarget> }) => {
                const nation = row.original;
                if (nation.beigeTurns <= 0) return <Text size="sm" c="dimmed">Not beige</Text>;
                return (
                  <Tooltip label={nation.hasReminderActive ? 'Remove reminder' : 'Set reminder'}>
                    <ActionIcon
                      variant={nation.hasReminderActive ? 'filled' : 'light'}
                      color={nation.hasReminderActive ? 'green' : 'gray'}
                      onClick={() => handleReminderToggle(row)}
                      loading={addReminderMutation.isPending || removeReminderMutation.isPending}
                    >
                      {nation.hasReminderActive ? <IconBell size={16} /> : <IconBellOff size={16} />}
                    </ActionIcon>
                  </Tooltip>
                );
              },
            } as MRT_ColumnDef<RaidTarget>,
          ]
        : showBeige
        ? [
            {
              accessorKey: 'beigeTurns',
              header: 'Beige Turns',
              Header: () => wrappedHeader('Beige Turns'),
              size: 120,
            } as MRT_ColumnDef<RaidTarget>,
          ]
        : []),
      {
        accessorKey: 'nationLoot',
        header: 'Beige Loot',
        Header: () => wrappedHeader('Beige Loot'),
        size: 120,
        mantineTableBodyCellProps: { align: 'right' },
      },
      {
        accessorKey: 'daysInactive',
        header: 'Days Inactive',
        Header: () => wrappedHeader('Days Inactive'),
        size: 130,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: minOnlyFilter,
        Filter: MinOnlyFilterInput,
      },
      {
        accessorKey: 'monetaryNetIncome',
        header: 'Net Income',
        Header: () => wrappedHeader('Net Income'),
        size: 130,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
        filterFn: minOnlyFilter,
        Filter: MinOnlyFilterInput,
      },
      {
        accessorKey: 'netCashIncome',
        header: 'Cash Income',
        Header: () => wrappedHeader('Cash Income'),
        size: 130,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
        filterFn: minOnlyFilter,
        Filter: MinOnlyFilterInput,
      },
      {
        accessorKey: 'taxable',
        header: 'Taxable', // Shortened
        size: 130,
        filterVariant: 'select',
        filterFn: booleanFilter,
        mantineFilterSelectProps: {
          data: [
            { value: 'true', label: 'Yes' },
            { value: 'false', label: 'No' },
          ],
          clearable: true,
        },
        Cell: ({ cell }) => (cell.getValue<boolean>() ? 'Yes' : 'No'),
      },
      {
        accessorKey: 'treasures',
        header: 'Treasures', // Abbreviated to fit
        size: 140,
        mantineTableBodyCellProps: { align: 'right' },
      },
      {
        accessorKey: 'defSlots',
        header: 'Used Defensive Slots',
        Header: () => wrappedHeader('Used Defensive Slots'),
        size: 145,
        Cell: ({ cell }) => `${cell.getValue<number>()}/3`,
        filterFn: maxOnlyFilter,
        Filter: MaxOnlyFilterInput,
      },
      {
        accessorKey: 'timeSinceWar',
        header: 'Days Since War',
        Header: () => wrappedHeader('Days Since War'),
        size: 130,
        filterFn: minOnlyFilter,
        Filter: MinOnlyFilterInput,
      },
      // Military columns 
      {
        accessorKey: 'soldiers',
        header: 'Soldiers',
        size: 130,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
        filterFn: rangeFilter,
        Filter: RangeFilterInput,
      },
      {
        accessorKey: 'tanks',
        header: 'Tanks',
        size: 120,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
        filterFn: rangeFilter,
        Filter: RangeFilterInput,
      },
      {
        accessorKey: 'aircraft',
        header: 'Aircraft',
        size: 130,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: rangeFilter,
        Filter: RangeFilterInput,
      },
      {
        accessorKey: 'ships',
        header: 'Ships',
        size: 120,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: rangeFilter,
        Filter: RangeFilterInput,
      },
      {
        accessorKey: 'missiles',
        header: 'Missiles',
        size: 130,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: rangeFilter,
        Filter: RangeFilterInput,
      },
      {
        accessorKey: 'nukes',
        header: 'Nukes',
        size: 120,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: rangeFilter,
        Filter: RangeFilterInput,
      },
      {
        accessorKey: 'groundWin',
        header: 'Ground Win %',
        Header: () => wrappedHeader('Ground Win %'),
        size: 130, // "Ground" needs ~50px + Icon ~20px + Padding
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `${cell.getValue<number>()}%`,
        filterFn: rangeFilter,
        Filter: RangeFilterInput,
      },
      {
        accessorKey: 'airWin',
        header: 'Air Win %',
        Header: () => wrappedHeader('Air Win %'),
        size: 120,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `${cell.getValue<number>()}%`,
        filterFn: rangeFilter,
        Filter: RangeFilterInput,
      },
      {
        accessorKey: 'navalWin',
        header: 'Naval Win %',
        Header: () => wrappedHeader('Naval Win %'),
        size: 130,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `${cell.getValue<number>()}%`,
        filterFn: rangeFilter,
        Filter: RangeFilterInput,
      },
      {
        accessorKey: 'totalWin',
        header: 'Total Win %',
        Header: () => wrappedHeader('Total Win %'),
        size: 130,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `${cell.getValue<number>()}%`,
        filterFn: rangeFilter,
        Filter: RangeFilterInput,
      },
      {
        id: 'actions',
        header: 'Actions',
        size: 110,
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
    [showBeige, discordLinked, handleReminderToggle, addReminderMutation.isPending, removeReminderMutation.isPending, uniqueAlliances, uniquePositions, uniqueColors, cityRange]
  );

  const table = useMantineReactTable({
    columns,
    data,
    enableColumnResizing: true,
    enableColumnOrdering: true,
    enablePagination: true,
    enableStickyHeader: true,
    enableRowVirtualization: data.length > 50,
    enableColumnFilters: true,
    enableFilters: true,

    filterFns: {
      minOnly: minOnlyFilter,
      maxOnly: maxOnlyFilter,
      range: rangeFilter,
    },

    globalFilterFn: 'contains',

    initialState: {
      columnFilters: initialFilters,
      sorting: initialSorting,
      pagination: { pageSize: 50, pageIndex: 0 },
      density: 'xs', 
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
      style: { maxHeight: '600px' },
    },
    mantineTableProps: {
      className: 'raids-table',
      style: { minWidth: '100%' },
      striped: true,
    },
    mantineTableHeadCellProps: {
      style: {
        padding: '4px',
        verticalAlign: 'bottom',
      },
    },
    mantinePaperProps: {
      shadow: 'sm',
      radius: 'md',
      withBorder: true,
    },
  });

  return (
    <Stack gap="md">
      <MantineReactTable table={table} />
      <Alert icon={<IconInfoCircle size={16} />} title="Pro Tip" color="blue" variant="light">
        You can customize this table by hiding/showing columns, reordering them, and adjusting the density.
        All your preferences are automatically saved and will be remembered the next time you visit using the same browser.
      </Alert>
    </Stack>
  );
}

function getColorBadge(color: string): string {
  const colorMap: Record<string, string> = {
    aqua: 'cyan', black: 'dark', blue: 'blue', brown: 'orange', green: 'green',
    lime: 'lime', maroon: 'red', olive: 'yellow', orange: 'orange', pink: 'pink',
    purple: 'grape', red: 'red', white: 'gray', yellow: 'yellow', beige: 'yellow', gray: 'gray',
  };
  return colorMap[color.toLowerCase()] || 'gray';
}