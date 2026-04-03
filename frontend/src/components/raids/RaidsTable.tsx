import { useMemo, useCallback, useState, useEffect, useRef, type ReactNode } from 'react';
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
  Text,
  Tooltip,
  Box,
  Alert,
  Stack,
  Group,
  Button,
  NumberInput,
  TextInput,
  Menu,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useDebouncedValue } from '@mantine/hooks';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  IconBell,
  IconBellOff,
  IconBrandDiscord,
  IconExternalLink,
  IconInfoCircle,
} from '@tabler/icons-react';
import { useLocation } from 'react-router-dom';

import type { RaidTarget } from '@/types';
import { addReminder, removeReminder } from '@/api';
import { getDiscordLoginUrl } from '@/api/auth';
import { internalNavPath } from '@/lib/internalNavPath';
import { parseNumericValue } from '@/lib/raidFilterParsing';

const relativeTimeFormatter = new Intl.RelativeTimeFormat(undefined, {
  numeric: 'auto',
});

const formatRelativeUpdatedAt = (unixSeconds: number): string => {
  const nowMs = Date.now();
  const tsMs = unixSeconds * 1000;
  const diffSeconds = Math.round((tsMs - nowMs) / 1000);
  const absSeconds = Math.abs(diffSeconds);

  if (!Number.isFinite(diffSeconds)) return '—';
  if (absSeconds < 5) return 'just now';
  if (absSeconds < 60) return relativeTimeFormatter.format(diffSeconds, 'second');

  const diffMinutes = Math.round(diffSeconds / 60);
  const absMinutes = Math.abs(diffMinutes);
  if (absMinutes < 60) return relativeTimeFormatter.format(diffMinutes, 'minute');

  const diffHours = Math.round(diffMinutes / 60);
  const absHours = Math.abs(diffHours);
  if (absHours < 24) return relativeTimeFormatter.format(diffHours, 'hour');

  const diffDays = Math.round(diffHours / 24);
  const absDays = Math.abs(diffDays);
  if (absDays < 30) return relativeTimeFormatter.format(diffDays, 'day');

  const diffMonths = Math.round(diffDays / 30);
  const absMonths = Math.abs(diffMonths);
  if (absMonths < 12) return relativeTimeFormatter.format(diffMonths, 'month');

  const diffYears = Math.round(diffDays / 365);
  return relativeTimeFormatter.format(diffYears, 'year');
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

// --- HEADER LABEL ---
// Up to 2 lines, centered; when the title area shrinks (e.g. filter icon appears), overflow is hidden
// with an ellipsis on the second line (see .raids-table thead rules for layout vs icons).
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

const headerWithTooltip = (text: string, description: string) => (
  <Tooltip label={description} multiline maw={260} withinPortal>
    {wrappedHeader(text)}
  </Tooltip>
);

/** Center content in the Reminder column; use fullWidth for bell / CTA controls. */
function ReminderColumnCell({ children, fullWidth = false }: { children: ReactNode; fullWidth?: boolean }) {
  return (
    <Box
      w="100%"
      maw="100%"
      style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: 36,
        ...(fullWidth ? { alignSelf: 'stretch' as const } : {}),
      }}
    >
      {fullWidth ? (
        <Box component="span" w="100%" maw="100%" style={{ display: 'block', minWidth: 0 }}>
          {children}
        </Box>
      ) : (
        children
      )}
    </Box>
  );
}

// --- CUSTOM FILTER COMPONENTS ---

function columnFilterString(value: unknown): string {
  if (value === undefined || value === null || value === '') return '';
  return String(value);
}

function numberInputValueFromFilterString(s: string): string | number {
  if (s === '') return '';
  const n = Number(s);
  return Number.isFinite(n) ? n : s;
}

// Filter component: Min only (income, loot, days inactive, etc.)
const MinOnlyFilterInput = ({ column, placeholder }: any) => {
  const colStr = columnFilterString(column.getFilterValue());
  const [raw, setRaw] = useState<string>(colStr);
  const [debounced] = useDebouncedValue(raw, 500);
  const lastEmittedRef = useRef(colStr);

  useEffect(() => {
    const next = debounced ?? '';
    lastEmittedRef.current = next;
    column.setFilterValue(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  // Sidebar / URL sync updates column state without remounting this cell — keep the input in sync.
  useEffect(() => {
    if (colStr !== lastEmittedRef.current) {
      lastEmittedRef.current = colStr;
      setRaw(colStr);
    }
  }, [colStr]);

  return (
    <TextInput
      placeholder={placeholder ?? 'Min (e.g. 10k, 2m)'}
      value={raw}
      onChange={(e) => setRaw(e.currentTarget.value)}
      size="xs"
    />
  );
};

// Generic Filter component: Max only (for military units)
const MaxOnlyFilterInput = ({ column, placeholder }: any) => {
  const colStr = columnFilterString(column.getFilterValue());
  const [raw, setRaw] = useState<string>(colStr);
  const [debounced] = useDebouncedValue(raw, 500);
  const lastEmittedRef = useRef(colStr);

  useEffect(() => {
    const next = debounced ?? '';
    lastEmittedRef.current = next;
    column.setFilterValue(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  useEffect(() => {
    if (colStr !== lastEmittedRef.current) {
      lastEmittedRef.current = colStr;
      setRaw(colStr);
    }
  }, [colStr]);

  return (
    <TextInput
      placeholder={placeholder || "Max (e.g. 500k)"}
      value={raw}
      onChange={(e) => setRaw(e.currentTarget.value)}
      size="xs"
    />
  );
};

// Numeric-only Min filter (for Days Since War and Win% columns)
const NumericMinOnlyFilterInput = ({ column, max }: any) => {
  const colStr = columnFilterString(column.getFilterValue());
  const [localValue, setLocalValue] = useState<any>(() => numberInputValueFromFilterString(colStr));
  const [debounced] = useDebouncedValue(localValue, 400);
  const lastEmittedRef = useRef(colStr);

  useEffect(() => {
    const next =
      debounced === '' || debounced === undefined || debounced === null ? '' : String(debounced);
    lastEmittedRef.current = next;
    column.setFilterValue(debounced ?? '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  useEffect(() => {
    if (colStr !== lastEmittedRef.current) {
      lastEmittedRef.current = colStr;
      setLocalValue(numberInputValueFromFilterString(colStr));
    }
  }, [colStr]);

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
  /** Alliance names for the column multi-select (from parent: full target list + current picks). Keeps options when filtered rows are empty. */
  allianceSelectOptions?: string[];
  /** Alliance positions for the column multi-select (from parent: unfiltered targets + picks). Keeps all roles visible while a position filter is active. */
  positionSelectOptions?: { value: string; label: string }[];
  discordAuthenticated: boolean;
  discordLinked: boolean;
  /** Opens Verify Nation (link PnW account). Used when signed in with Discord but not linked. */
  onOpenVerifyNationModal?: () => void;
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
  allianceSelectOptions,
  positionSelectOptions,
  discordAuthenticated,
  discordLinked,
  onOpenVerifyNationModal,
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
  const location = useLocation();
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    nation: RaidTarget;
  } | null>(null);

  // ... (Keep your mutations same as before) ...
  const addReminderMutation = useMutation({
    mutationFn: (nationId: number) => {
      if (!discordLinked) return Promise.reject(new Error('Login with Discord to use reminders'));
      return addReminder({ nationId });
    },
    onSuccess: (_, nationId) => {
      notifications.show({ title: 'Reminder Set', message: `Nation ${nationId}`, color: 'green' });
      queryClient.setQueriesData<{ targets: RaidTarget[] }>({ queryKey: ['raids'] }, (old) => {
        if (!old) return old;
        return { ...old, targets: old.targets.map((t) => t.id === nationId ? { ...t, hasReminderActive: true } : t) };
      });
    },
    onError: (error: Error) => notifications.show({ title: 'Error', message: error.message, color: 'red' }),
  });

  const removeReminderMutation = useMutation({
    mutationFn: (nationId: number) => {
      if (!discordLinked) return Promise.reject(new Error('Login with Discord to use reminders'));
      return removeReminder(nationId);
    },
    onSuccess: (_, nationId) => {
      notifications.show({ title: 'Reminder Removed', message: `Nation ${nationId}`, color: 'blue' });
      queryClient.setQueriesData<{ targets: RaidTarget[] }>({ queryKey: ['raids'] }, (old) => {
        if (!old) return old;
        return { ...old, targets: old.targets.map((t) => t.id === nationId ? { ...t, hasReminderActive: false } : t) };
      });
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
    if (allianceSelectOptions !== undefined) {
      return [...allianceSelectOptions].sort((a, b) => a.localeCompare(b));
    }
    const alliances = new Set(data.map((d) => d.allianceName).filter((a) => a && a !== 'None'));
    return Array.from(alliances).sort();
  }, [data, allianceSelectOptions]);

  const uniquePositions = useMemo(() => {
    if (positionSelectOptions !== undefined && positionSelectOptions.length > 0) {
      return [...positionSelectOptions].sort((a, b) => a.label.localeCompare(b.label));
    }
    const positions = new Set(data.map((d) => d.alliancePosition).filter(Boolean));
    const opts = Array.from(positions).map((p) => ({
      value: p as string,
      label: p === 'NOALLIANCE' ? 'None' : (p as string).toLowerCase(),
    }));
    return opts.sort((a, b) => a.label.localeCompare(b.label));
  }, [data, positionSelectOptions]);

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
        size: 70, 
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
        size: 110,
        filterVariant: 'multi-select',
        mantineFilterMultiSelectProps: {
          data: uniquePositions,
          clearable: true,
          hidePickedOptions: false,
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
          minRange: 0,
        },
        size: 90, // Increased slightly to fit "Cities" + Icon
      },
      {
        accessorKey: 'color',
        header: 'Color',
        size: 110,
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
      {
        accessorKey: 'beigeTurns',
        header: 'Beige Turns',
        size: 90,
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
        header: 'Reminder',
        Header: () =>
          discordLinked ? (
            wrappedHeader('Reminder')
          ) : (
            <Tooltip
              label={
                discordAuthenticated
                  ? onOpenVerifyNationModal
                    ? 'Link your PnW nation via Link nation in each row, the yellow banner, or the sidebar.'
                    : 'Link your PnW nation using Verify Nation on this site or /verify in the Discord bot, then refresh.'
                  : 'Use Log in with Discord in each row, the sidebar, or the raids banner.'
              }
              multiline
              maw={280}
              withinPortal
            >
              <Box style={{ cursor: 'help' }}>{wrappedHeader('Reminder')}</Box>
            </Tooltip>
          ),
        size:
          !discordLinked && discordAuthenticated && onOpenVerifyNationModal
            ? 128
            : !discordLinked
              ? 176
              : 120,
        enableSorting: false,
        enableColumnFilter: false,
        mantineTableBodyCellProps: {
          style: { verticalAlign: 'middle' },
        },
        Cell: ({ row }: { row: MRT_Row<RaidTarget> }) => {
          const nation = row.original;
          if (nation.beigeTurns <= 0) {
            return (
              <ReminderColumnCell>
                <Text size="sm" c="dimmed" ta="center" style={{ width: '100%' }}>
                  Not beige
                </Text>
              </ReminderColumnCell>
            );
          }
          if (!discordLinked) {
            if (!discordAuthenticated) {
              return (
                <ReminderColumnCell fullWidth>
                  <Button
                    size="xs"
                    variant="light"
                    component="a"
                    href={getDiscordLoginUrl('/raids')}
                    leftSection={<IconBrandDiscord size={14} />}
                    fullWidth
                  >
                    Log in with Discord
                  </Button>
                </ReminderColumnCell>
              );
            }
            if (onOpenVerifyNationModal) {
              return (
                <ReminderColumnCell fullWidth>
                  <Button
                    size="xs"
                    variant="light"
                    fullWidth
                    onClick={() => onOpenVerifyNationModal()}
                  >
                    Link nation
                  </Button>
                </ReminderColumnCell>
              );
            }
            const disabledHint =
              'Link your PnW nation using Verify Nation on this site or /verify in the Discord bot, then refresh.';
            return (
              <ReminderColumnCell fullWidth>
                <Tooltip label={disabledHint} multiline maw={280} withinPortal>
                  <Box component="span" w="100%" style={{ display: 'block' }}>
                    <ActionIcon
                      variant="light"
                      color="gray"
                      size="lg"
                      radius="md"
                      w="100%"
                      disabled
                      aria-label={disabledHint}
                    >
                      <IconBellOff size={18} />
                    </ActionIcon>
                  </Box>
                </Tooltip>
              </ReminderColumnCell>
            );
          }
          return (
            <ReminderColumnCell fullWidth>
              <Tooltip label={nation.hasReminderActive ? 'Remove reminder' : 'Set reminder'}>
                <Box component="span" w="100%" style={{ display: 'block' }}>
                  <ActionIcon
                    variant={nation.hasReminderActive ? 'filled' : 'light'}
                    color={nation.hasReminderActive ? 'green' : 'gray'}
                    size="lg"
                    radius="md"
                    w="100%"
                    onClick={() => handleReminderToggle(row)}
                    loading={addReminderMutation.isPending || removeReminderMutation.isPending}
                  >
                    {nation.hasReminderActive ? <IconBell size={20} /> : <IconBellOff size={20} />}
                  </ActionIcon>
                </Box>
              </Tooltip>
            </ReminderColumnCell>
          );
        },
      } as MRT_ColumnDef<RaidTarget>,
      {
        accessorKey: 'nationLoot',
        header: 'Beige Loot',
        size: 100,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: minOnlyFilter,
        Filter: MinOnlyFilterInput,
      },
      {
        accessorKey: 'daysInactive',
        header: 'Days Inactive',
        size: 105,
        mantineTableBodyCellProps: { align: 'center' },
        filterFn: minOnlyFilter,
        Filter: (props) => (
          <MinOnlyFilterInput {...props} placeholder="Min days (e.g. 7, 30)" />
        ),
      },
      {
        accessorKey: 'updatedAt',
        header: 'Data Age',
        Header: () =>
          headerWithTooltip(
            'Data Age',
            'How old the cached nation data is (when Autolycus last refreshed it).',
          ),
        size: 165,
        enableColumnFilter: false,
        mantineTableBodyCellProps: { align: 'center' },
        Cell: ({ cell }) => {
          const ts = cell.getValue<number | null | undefined>();
          if (ts == null) return '—';
          const ms = Number(ts) * 1000;
          if (!Number.isFinite(ms) || ms <= 0) return '—';
          const exact = new Date(ms).toLocaleString();
          const relative = formatRelativeUpdatedAt(Number(ts));
          return (
            <Tooltip label={exact} withArrow withinPortal>
              <Text span>{relative}</Text>
            </Tooltip>
          );
        },
      },
      {
        accessorKey: 'monetaryNetIncome',
        header: 'Net Income',
        Header: () => headerWithTooltip('Net Income', 'Total resource gain/loss valued at current prices (cash + resources).'),
        size: 105,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
        filterFn: minOnlyFilter,
        Filter: MinOnlyFilterInput,
      },
      {
        accessorKey: 'netCashIncome',
        header: 'Cash Income',
        Header: () => headerWithTooltip('Cash Income', 'Net cash-only income (excludes the value of produced resources).'),
        size: 105,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `$${cell.getValue<number>().toLocaleString()}`,
        filterFn: minOnlyFilter,
        Filter: MinOnlyFilterInput,
      },
      {
        accessorKey: 'taxable',
        header: 'Taxable', // Shortened
        size: 105,
        filterVariant: 'select',
        filterFn: booleanFilter,
        mantineTableBodyCellProps: { align: 'center' },
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
        size: 120,
        mantineTableBodyCellProps: { align: 'center' },
      },
      {
        accessorKey: 'defSlots',
        header: 'Used Def. Slots',
        size: 140,
        mantineTableBodyCellProps: { align: 'center' },
        filterFn: maxOnlyFilter,
        filterVariant: 'select',
        mantineFilterSelectProps: {
          data: [
            { value: '0', label: '0' },
            { value: '1', label: '1' },
            { value: '2', label: '2' },
            { value: '3', label: '3' },
          ],
          placeholder: 'Max',
          clearable: true,
        },
      },
      {
        accessorKey: 'timeSinceWar',
        header: 'Days Since War',
        size: 120,
        mantineTableBodyCellProps: { align: 'center' },
        filterFn: minOnlyFilter,
        Filter: NumericMinOnlyFilterInput,
      },
      // Military columns 
      {
        accessorKey: 'soldiers',
        header: 'Soldiers',
        size: 110,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
        filterFn: maxOnlyFilter,
        Filter: MaxOnlyFilterInput,
      },
      {
        accessorKey: 'tanks',
        header: 'Tanks',
        size: 90,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => cell.getValue<number>().toLocaleString(),
        filterFn: maxOnlyFilter,
        Filter: ({ column }) => <MaxOnlyFilterInput column={column} placeholder="Max (e.g. 20k)" />,
      },
      {
        accessorKey: 'aircraft',
        header: 'Aircraft',
        size: 105,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: maxOnlyFilter,
        Filter: ({ column }) => <MaxOnlyFilterInput column={column} placeholder="Max (e.g. 2k)" />,
      },
      {
        accessorKey: 'ships',
        header: 'Ships',
        size: 90,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: maxOnlyFilter,
        Filter: ({ column }) => <MaxOnlyFilterInput column={column} placeholder="Max (e.g. 400)" />,
      },
      {
        accessorKey: 'missiles',
        header: 'Missiles',
        size: 105,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: maxOnlyFilter,
        Filter: ({ column }) => <MaxOnlyFilterInput column={column} placeholder="Max (e.g. 50)" />,
      },
      {
        accessorKey: 'nukes',
        header: 'Nukes',
        size: 95,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: maxOnlyFilter,
        Filter: ({ column }) => <MaxOnlyFilterInput column={column} placeholder="Max (e.g. 20)" />,
      },
      {
        accessorKey: 'groundWin',
        header: 'Ground Win %',
        size: 105, // "Ground" needs ~50px + Icon ~20px + Padding
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `${cell.getValue<number>()}%`,
        filterFn: minOnlyFilter,
        Filter: ({ column }) => <NumericMinOnlyFilterInput column={column} max={100} />,
      },
      {
        accessorKey: 'airWin',
        header: 'Air Win %',
        size: 100,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `${cell.getValue<number>()}%`,
        filterFn: minOnlyFilter,
        Filter: ({ column }) => <NumericMinOnlyFilterInput column={column} max={100} />,
      },
      {
        accessorKey: 'navalWin',
        header: 'Naval Win %',
        size: 100,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `${cell.getValue<number>()}%`,
        filterFn: minOnlyFilter,
        Filter: ({ column }) => <NumericMinOnlyFilterInput column={column} max={100} />,
      },
      {
        accessorKey: 'totalWin',
        header: 'Total Win %',
        size: 100,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => `${cell.getValue<number>()}%`,
        filterFn: minOnlyFilter,
        Filter: ({ column }) => <NumericMinOnlyFilterInput column={column} max={100} />,
      },

    ],
    [
      discordLinked,
      discordAuthenticated,
      onOpenVerifyNationModal,
      handleReminderToggle,
      addReminderMutation.isPending,
      removeReminderMutation.isPending,
      uniqueAlliances,
      uniquePositions,
      uniqueColors,
      cityRange,
    ]
  );

  const table = useMantineReactTable({
    columns,
    data,
    defaultColumn: {
      Header: ({ column }) => {
        const h = column.columnDef.header;
        return typeof h === 'string' ? wrappedHeader(h) : null;
      },
    },
    enableColumnResizing: true,
    enableColumnOrdering: true,
    enableColumnDragging: false,
    enablePagination: true,
    enableStickyHeader: true,
    enableRowVirtualization: data.length > 50,
    enableColumnFilters: true,
    enableFilters: true,
    enableDensityToggle: false,

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
      px: 'lg',
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
          {contextMenu && contextMenu.nation.allianceId !== '0' ? (
            <Menu.Item
              leftSection={<IconExternalLink size={16} />}
              component="a"
              href={`https://politicsandwar.com/alliance/id=${contextMenu.nation.allianceId}`}
              target="_blank"
            >
              Open alliance page
            </Menu.Item>
          ) : (
            <Menu.Item
              leftSection={<IconExternalLink size={16} />}
              disabled
            >
              Open alliance page
            </Menu.Item>
          )}
          <Menu.Item
            leftSection={<IconExternalLink size={16} />}
            component="a"
            href={contextMenu ? `https://politicsandwar.com/nation/war/declare/id=${contextMenu.nation.id}` : '#'}
            target="_blank"
          >
            Declare war
          </Menu.Item>
          <Menu.Item
            leftSection={<IconExternalLink size={16} />}
            component="a"
            href={internalNavPath('/reminders', location.search)}
          >
            Manage reminders
          </Menu.Item>
          <Menu.Divider />
          <Menu.Item
            leftSection={
              contextMenu?.nation.hasReminderActive ? <IconBell size={16} /> : <IconBellOff size={16} />
            }
            disabled={(() => {
              if (!contextMenu || contextMenu.nation.beigeTurns <= 0) return true;
              if (discordLinked) return false;
              if (discordAuthenticated && onOpenVerifyNationModal) return false;
              return true;
            })()}
            onClick={() => {
              if (!contextMenu) return;
              const nation = contextMenu.nation;
              if (nation.beigeTurns <= 0) return;
              if (!discordLinked && discordAuthenticated && onOpenVerifyNationModal) {
                setContextMenu(null);
                onOpenVerifyNationModal();
                return;
              }
              if (discordLinked) toggleReminderForNation(nation);
            }}
          >
            {!discordLinked &&
            discordAuthenticated &&
            onOpenVerifyNationModal &&
            contextMenu &&
            contextMenu.nation.beigeTurns > 0
              ? 'Link nation to set reminders'
              : contextMenu?.nation.hasReminderActive
                ? 'Remove beige reminder'
                : 'Add beige reminder'}
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>
      <MantineReactTable table={table} />
      {discordAuthenticated && !discordLinked && (
        <Alert icon={<IconInfoCircle size={16} />} title="Reminder setup" color="yellow" variant="light">
          <Group justify="space-between" align="flex-start" wrap="wrap" gap="sm">
            <Text size="sm">
              Link your Politics & War nation in <strong>Verify Nation</strong> (same as the yellow banner above
              {onOpenVerifyNationModal ? ' or the Link nation buttons in the Reminder column' : ''}) to enable beige
              reminders. You can also use <strong>/verify</strong> in the Discord bot.
            </Text>
            {onOpenVerifyNationModal ? (
              <Button size="xs" variant="default" onClick={() => onOpenVerifyNationModal()}>
                Verify Nation
              </Button>
            ) : null}
          </Group>
        </Alert>
      )}
      <Alert icon={<IconInfoCircle size={16} />} title="Pro Tip" color="blue" variant="light">
        Hide or show columns, reorder them and filter columns by using the controls in the top-right of the table.
        Right-click any row to open a context menu with quick links to the nation page, alliance page, declare war page, or to set a beige reminder.
        Use Manage reminders for timing offsets and bulk cleanup.
      </Alert>
    </Stack>
  );
}

function getColorBadge(color: string): string {
  const colorMap: Record<string, string> = {
    aqua: 'cyan',
    black: 'gray',
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
    grey: 'gray',
    gold: 'yellow',
    lavender: 'violet',
    turquoise: 'cyan',
    teal: 'teal',
  };
  return colorMap[color.toLowerCase()] || 'gray';
}