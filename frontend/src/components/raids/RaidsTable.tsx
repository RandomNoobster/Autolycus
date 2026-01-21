import { useMemo, useCallback, useState, useEffect } from 'react';
import {
  MantineReactTable,
  useMantineReactTable,
  type MRT_ColumnDef,
  type MRT_Row,
  type MRT_ColumnFiltersState,
  type MRT_ColumnOrderState,
  type MRT_DensityState,
  type MRT_VisibilityState,
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
  TextInput,
  Menu,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useDebouncedValue } from '@mantine/hooks';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { IconBell, IconBellOff, IconExternalLink, IconInfoCircle } from '@tabler/icons-react';

import type { RaidTarget } from '@/types';
import { addReminder, removeReminder } from '@/api';

// --- HELPER FUNCTIONS FOR FILTERING ---

// Parse numeric values that might contain $, %, +, commas, and k/m/b suffix
const parseNumericValue = (value: unknown): number => {
  if (typeof value === 'number') return value;
  if (typeof value === 'string') {
    const s = value.trim().toLowerCase();
    // Remove common formatting but keep potential k/m/b suffix
    const cleaned = s.replace(/[,$%+\s]/g, '');
    const match = cleaned.match(/^(-?\d*\.?\d+)([kmb])?$/i);
    if (match) {
      const base = parseFloat(match[1]);
      const suf = (match[2] || '').toLowerCase();
      const mult = suf === 'k' ? 1e3 : suf === 'm' ? 1e6 : suf === 'b' ? 1e9 : 1;
      const num = base * mult;
      return isNaN(num) ? 0 : num;
    }
    const parsed = parseFloat(cleaned.replace(/[^0-9.-]/g, ''));
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

const beigeFilter = (row: any, id: string, filterValue: any) => {
  if (!filterValue) return true;
  const turns = parseNumericValue(row.getValue(id));
  if (filterValue === 'only') return turns > 0;
  if (filterValue === 'hide') return turns <= 0;
  return true;
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

const headerWithTooltip = (text: string, description: string) => (
  <Tooltip label={description} multiline maw={260} withinPortal>
    {wrappedHeader(text)}
  </Tooltip>
);

// --- CUSTOM FILTER COMPONENTS ---

// Filter component: Min only (for days inactive, income fields, days since war)
const MinOnlyFilterInput = ({ column }: any) => {
  const initial = String(column.getFilterValue() ?? '');
  const [raw, setRaw] = useState<string>(initial);
  const [debounced] = useDebouncedValue(raw, 500);

  useEffect(() => {
    column.setFilterValue(debounced ?? '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  return (
    <TextInput
      placeholder="Min (e.g. 10k, 2m)"
      value={raw}
      onChange={(e) => setRaw(e.currentTarget.value)}
      size="xs"
    />
  );
};

// Generic Filter component: Max only (for military units)
const MaxOnlyFilterInput = ({ column, placeholder }: any) => {
  const initial = String(column.getFilterValue() ?? '');
  const [raw, setRaw] = useState<string>(initial);
  const [debounced] = useDebouncedValue(raw, 500);

  useEffect(() => {
    column.setFilterValue(debounced ?? '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  return (
    <TextInput
      placeholder={placeholder || "Max (e.g. 500k)"}
      value={raw}
      onChange={(e) => setRaw(e.currentTarget.value)}
      size="xs"
    />
  );
};

// Specialized Filter component: Max only with cap (for defensive slots up to 3)
const DefSlotsMaxOnlyFilterInput = ({ column }: any) => {
  const initial = String(column.getFilterValue() ?? '');
  const [raw, setRaw] = useState<string>(initial);
  const [debounced] = useDebouncedValue(raw, 400);

  useEffect(() => {
    const parsed = parseNumericValue(debounced);
    const clamped = Math.min(Math.max(parsed, 0), 3);
    column.setFilterValue(String(Number.isFinite(clamped) ? clamped : ''));
    // reflect clamped value to input to avoid confusion
    if (parsed !== clamped) setRaw(String(clamped));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  return (
    <TextInput
      placeholder="Max (0-3)"
      value={raw}
      onChange={(e) => setRaw(e.currentTarget.value)}
      size="xs"
    />
  );
};


// Numeric-only Min filter (for Days Since War and Win% columns)
const NumericMinOnlyFilterInput = ({ column, max }: any) => {
  const initial = column.getFilterValue() ?? '';
  const [localValue, setLocalValue] = useState<any>(initial);
  const [debounced] = useDebouncedValue(localValue, 400);

  useEffect(() => {
    column.setFilterValue(debounced ?? '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  return (
    <NumberInput
      placeholder="Min"
      value={localValue}
      onChange={(val) => setLocalValue(val ?? '')}
      size="xs"
      min={0}
      max={typeof max === 'number' ? max : undefined}
    />
  );
};

interface RaidsTableProps {
  data: RaidTarget[];
  token: string;
  showBeige: boolean;
  discordLinked: boolean;
  initialSorting?: { id: string; desc: boolean }[];
  columnVisibility: MRT_VisibilityState;
  columnOrder: MRT_ColumnOrderState;
  density: MRT_DensityState;
  columnFilters: MRT_ColumnFiltersState;
  onColumnVisibilityChange: (
    updater: MRT_VisibilityState | ((prev: MRT_VisibilityState) => MRT_VisibilityState)
  ) => void;
  onColumnOrderChange: (
    updater: MRT_ColumnOrderState | ((prev: MRT_ColumnOrderState) => MRT_ColumnOrderState)
  ) => void;
  onDensityChange: (updater: MRT_DensityState | ((prev: MRT_DensityState) => MRT_DensityState)) => void;
  onColumnFiltersChange: (updater: MRT_ColumnFiltersState) => void;
}

export function RaidsTable({
  data,
  token,
  showBeige,
  discordLinked,
  initialSorting = [],
  columnVisibility,
  columnOrder,
  density,
  columnFilters,
  onColumnVisibilityChange,
  onColumnOrderChange,
  onDensityChange,
  onColumnFiltersChange,
}: RaidsTableProps) {
  const queryClient = useQueryClient();
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    nation: RaidTarget;
  } | null>(null);

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

  const toggleReminderForNation = useCallback((nation: RaidTarget) => {
    nation.hasReminderActive ? removeReminderMutation.mutate(nation.id) : addReminderMutation.mutate(nation.id);
  }, [addReminderMutation, removeReminderMutation]);

  const handleReminderToggle = useCallback((row: MRT_Row<RaidTarget>) => {
    toggleReminderForNation(row.original);
  }, [toggleReminderForNation]);

  useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    window.addEventListener('click', close);
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    return () => {
      window.removeEventListener('click', close);
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
    };
  }, [contextMenu]);

  // Get unique values for filters
  const uniqueAlliances = useMemo(() => {
    const alliances = new Set(data.map(d => d.allianceName).filter(a => a && a !== 'None'));
    return Array.from(alliances).sort();
  }, [data]);

  const uniquePositions = useMemo(() => {
    const positions = new Set(data.map(d => d.alliancePosition).filter(p => p));
    const opts = Array.from(positions).map((p) => ({
      value: p as string,
      label: p === 'NOALLIANCE' ? 'None' : (p as string).toLowerCase(),
    }));
    return opts.sort((a, b) => a.label.localeCompare(b.label));
  }, [data]);

  const uniqueColors = useMemo(() => {
    const colors = new Set(data.map(d => d.color));
    return Array.from(colors).sort();
  }, [data]);

  const cityRange = useMemo(() => {
    const cities = data.map(d => d.numCities);
    if (!cities.length) return [0, 0];
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
              filterFn: beigeFilter,
              filterVariant: 'select',
              mantineFilterSelectProps: {
                data: [
                  { value: 'only', label: 'Only beige' },
                  { value: 'hide', label: 'Hide beige' },
                ],
                clearable: true,
              },
            } as MRT_ColumnDef<RaidTarget>,
            {
              id: 'reminder',
              header: 'Reminder', // Shortened text
              size: 120,
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
              filterFn: beigeFilter,
              filterVariant: 'select',
              mantineFilterSelectProps: {
                data: [
                  { value: 'only', label: 'Only beige' },
                  { value: 'hide', label: 'Hide beige' },
                ],
                clearable: true,
              },
            } as MRT_ColumnDef<RaidTarget>,
          ]
        : []),
      {
        accessorKey: 'nationLoot',
        header: 'Beige Loot',
        Header: () => wrappedHeader('Beige Loot'),
        size: 120,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: minOnlyFilter,
        Filter: MinOnlyFilterInput,
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
        Header: () => headerWithTooltip('Net Income', 'Total resource gain/loss valued at current prices (cash + resources).'),
        size: 130,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
        filterFn: minOnlyFilter,
        Filter: MinOnlyFilterInput,
      },
      {
        accessorKey: 'netCashIncome',
        header: 'Cash Income',
        Header: () => headerWithTooltip('Cash Income', 'Net cash-only income (excludes the value of produced resources).'),
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
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: maxOnlyFilter,
        Filter: DefSlotsMaxOnlyFilterInput,
      },
      {
        accessorKey: 'timeSinceWar',
        header: 'Days Since War',
        Header: () => wrappedHeader('Days Since War'),
        size: 130,
        filterFn: minOnlyFilter,
        Filter: NumericMinOnlyFilterInput,
      },
      // Military columns 
      {
        accessorKey: 'soldiers',
        header: 'Soldiers',
        size: 130,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
        filterFn: maxOnlyFilter,
        Filter: MaxOnlyFilterInput,
      },
      {
        accessorKey: 'tanks',
        header: 'Tanks',
        size: 120,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
        filterFn: maxOnlyFilter,
        Filter: ({ column }) => <MaxOnlyFilterInput column={column} placeholder="Max (e.g. 20k)" />,
      },
      {
        accessorKey: 'aircraft',
        header: 'Aircraft',
        size: 130,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: maxOnlyFilter,
        Filter: ({ column }) => <MaxOnlyFilterInput column={column} placeholder="Max (e.g. 2k)" />,
      },
      {
        accessorKey: 'ships',
        header: 'Ships',
        size: 120,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: maxOnlyFilter,
        Filter: ({ column }) => <MaxOnlyFilterInput column={column} placeholder="Max (e.g. 400)" />,
      },
      {
        accessorKey: 'missiles',
        header: 'Missiles',
        size: 130,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: maxOnlyFilter,
        Filter: ({ column }) => <MaxOnlyFilterInput column={column} placeholder="Max (e.g. 50)" />,
      },
      {
        accessorKey: 'nukes',
        header: 'Nukes',
        size: 120,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: maxOnlyFilter,
        Filter: ({ column }) => <MaxOnlyFilterInput column={column} placeholder="Max (e.g. 20)" />,
      },
      {
        accessorKey: 'groundWin',
        header: 'Ground Win %',
        Header: () => wrappedHeader('Ground Win %'),
        size: 130, // "Ground" needs ~50px + Icon ~20px + Padding
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `${cell.getValue<number>()}%`,
        filterFn: minOnlyFilter,
        Filter: ({ column }) => <NumericMinOnlyFilterInput column={column} max={100} />,
      },
      {
        accessorKey: 'airWin',
        header: 'Air Win %',
        Header: () => wrappedHeader('Air Win %'),
        size: 120,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `${cell.getValue<number>()}%`,
        filterFn: minOnlyFilter,
        Filter: ({ column }) => <NumericMinOnlyFilterInput column={column} max={100} />,
      },
      {
        accessorKey: 'navalWin',
        header: 'Naval Win %',
        Header: () => wrappedHeader('Naval Win %'),
        size: 130,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `${cell.getValue<number>()}%`,
        filterFn: minOnlyFilter,
        Filter: ({ column }) => <NumericMinOnlyFilterInput column={column} max={100} />,
      },
      {
        accessorKey: 'totalWin',
        header: 'Total Win %',
        Header: () => wrappedHeader('Total Win %'),
        size: 130,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `${cell.getValue<number>()}%`,
        filterFn: minOnlyFilter,
        Filter: ({ column }) => <NumericMinOnlyFilterInput column={column} max={100} />,
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
      columnFilters,
      sorting: initialSorting,
      pagination: { pageSize: 50, pageIndex: 0 },
      density,
    },
    state: {
      columnVisibility,
      columnOrder,
      density,
      columnFilters,
    },
    onColumnVisibilityChange,
    onColumnOrderChange,
    onDensityChange,
    onColumnFiltersChange: (updater) => {
      const nextFilters =
        typeof updater === 'function' ? updater(columnFilters) : updater;
      onColumnFiltersChange(nextFilters);
    },
    
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
    mantineTableBodyRowProps: ({ row }) => ({
      onContextMenu: (event) => {
        event.preventDefault();
        setContextMenu({
          x: event.clientX,
          y: event.clientY,
          nation: row.original,
        });
      },
    }),
    mantinePaperProps: {
      shadow: 'sm',
      radius: 'md',
      withBorder: true,
    },
  });

  return (
    <Stack gap="md">
      <Menu
        opened={!!contextMenu}
        onClose={() => setContextMenu(null)}
        withinPortal
        position="bottom-start"
        shadow="md"
      >
        <Menu.Target>
          <Box
            style={{
              position: 'fixed',
              top: contextMenu?.y ?? -1000,
              left: contextMenu?.x ?? -1000,
              width: 1,
              height: 1,
            }}
          />
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item
            leftSection={<IconExternalLink size={16} />}
            component="a"
            href={contextMenu ? `https://politicsandwar.com/nation/id=${contextMenu.nation.id}` : '#'}
            target="_blank"
          >
            Open nation page
          </Menu.Item>
          <Menu.Item
            leftSection={<IconExternalLink size={16} />}
            component="a"
            href={
              contextMenu && contextMenu.nation.allianceId !== '0'
                ? `https://politicsandwar.com/alliance/id=${contextMenu.nation.allianceId}`
                : '#'
            }
            target="_blank"
            disabled={!contextMenu || contextMenu.nation.allianceId === '0'}
          >
            Open alliance page
          </Menu.Item>
          <Menu.Item
            leftSection={<IconExternalLink size={16} />}
            component="a"
            href={contextMenu ? `https://politicsandwar.com/nation/war/declare/id=${contextMenu.nation.id}` : '#'}
            target="_blank"
          >
            Declare war
          </Menu.Item>
          <Menu.Divider />
          <Menu.Item
            leftSection={
              contextMenu?.nation.hasReminderActive ? <IconBell size={16} /> : <IconBellOff size={16} />
            }
            disabled={!contextMenu || !discordLinked || contextMenu.nation.beigeTurns <= 0}
            onClick={() => {
              if (!contextMenu) return;
              toggleReminderForNation(contextMenu.nation);
            }}
          >
            {contextMenu?.nation.hasReminderActive ? 'Remove beige reminder' : 'Add beige reminder'}
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>
      <MantineReactTable table={table} />
      <Alert icon={<IconInfoCircle size={16} />} title="Pro Tip" color="blue" variant="light">
        Hide or show columns, reorder them, adjust density, and filter columns directly in the table.
        When a custom template is active, every tweak is saved with it; built-in templates stay locked.
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