import {
  useMemo,
  useCallback,
  useState,
  useEffect,
  type Dispatch,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
  type SetStateAction,
} from 'react';
import {
  MantineReactTable,
  useMantineReactTable,
  type MRT_ColumnDef,
  type MRT_Row,
  type MRT_ColumnFiltersState,
  type MRT_ColumnOrderState,
  type MRT_VisibilityState,
  type MRT_TableInstance,
  type MRT_Column,
} from 'mantine-react-table';
import {
  Anchor,
  Badge,
  Text,
  Tooltip,
  Box,
  Alert,
  Stack,
  Button,
  Menu,
  MultiSelect,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useMutation, useMutationState, useQueryClient } from '@tanstack/react-query';
import {
  IconBell,
  IconBellOff,
  IconBrandDiscord,
  IconChartBar,
  IconExternalLink,
  IconInfoCircle,
} from '@tabler/icons-react';
import { useLocation, useNavigate, type NavigateFunction } from 'react-router-dom';

import type { RaidTarget } from '@/types';
import { addReminder, removeReminder } from '@/api';
import { getDiscordLoginUrl } from '@/api/auth';
import { internalNavPath } from '@/lib/internalNavPath';
import { parseNumericValue } from '@/lib/raidFilterParsing';
import {
  DebouncedTextFilterInput,
  MRT_RAIDS_BODY_CELL_PAD,
  NumericMinOnlyFilterInput,
  headerWithTooltip,
  maxOnlyFilter,
  minOnlyFilter,
  wrappedHeader,
} from '@/lib/mrtRaidsTableUi';
import { MrtTableToolbarInternalActions } from '@/lib/mrtTableToolbar';
import { buildRaidsCsv, downloadCsv, raidsCsvFilename } from '@/lib/raidsCsvExport';
import { REMINDERS_QUERY_KEY } from '@/lib/reminderDelivery';

const relativeTimeFormatter = new Intl.RelativeTimeFormat(undefined, {
  numeric: 'auto',
});

/** Menu.Item as `<a>` is unmounted on close before the browser follows the link; use SPA navigate for same-tab clicks. */
function handleSpaMenuAnchorClick(
  e: ReactMouseEvent<HTMLAnchorElement>,
  navigate: NavigateFunction,
  to: string,
  afterNavigate: () => void
) {
  if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
  e.preventDefault();
  navigate(to);
  afterNavigate();
}

/** External links in the menu hit the same unmount issue (even with target=_blank); open explicitly. */
function handleExternalMenuLink(e: ReactMouseEvent<HTMLAnchorElement>, after: () => void) {
  if (e.type === 'auxclick' && e.button !== 1) return;
  const raw = e.currentTarget.getAttribute('href');
  if (!raw || raw === '#' || !raw.startsWith('http')) return;
  e.preventDefault();
  window.open(raw, '_blank', 'noopener,noreferrer');
  after();
}

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


/** The only part of a table row the custom filter fns use. */
type FilterableRow = Pick<MRT_Row<RaidTarget>, 'getValue'>;

/** Money with the sign before the dollar: -$12,345 rather than $-12,345. */
function formatMoney(value: number | null | undefined): string {
  const n = Number(value ?? 0);
  return `${n < 0 ? '-' : ''}$${Math.abs(n).toLocaleString()}`;
}

/** Days since war for sorting/filtering: "14+" (no war in the cached window) sorts above every count. */
function timeSinceWarDays(value: RaidTarget['timeSinceWar']): number {
  return value === '14+' ? Number.POSITIVE_INFINITY : Number(value);
}

function winCell(value: number | null): string {
  return value == null ? '—' : `${value}%`;
}

const beigeFilter = (row: FilterableRow, id: string, filterValue: unknown) => {
  if (!filterValue) return true;
  const turns = parseNumericValue(row.getValue(id));
  if (filterValue === 'only') return turns > 0;
  if (filterValue === 'hide') return turns <= 0;
  return true;
};

/** Multi-select alliance names: row matches if alliance name equals any selected value (case-insensitive). */
function allianceNameMultiSelectFilterFn(row: FilterableRow, id: string, filterValue: unknown) {
  if (filterValue == null || filterValue === '') return true;
  const arr = Array.isArray(filterValue) ? filterValue : [filterValue];
  const strArr = arr.map((v) => String(v).trim()).filter(Boolean);
  if (!strArr.length) return true;
  const cell = String(row.getValue(id) ?? '');
  return strArr.some((v) => v.toLowerCase() === cell.toLowerCase());
}

// Custom filter: boolean filter for taxable
const booleanFilter = (row: FilterableRow, id: string, filterValue: unknown) => {
  if (filterValue === undefined || filterValue === null || filterValue === '') return true;
  const cellValue = row.getValue(id);
  const filterBool = filterValue === 'true' || filterValue === true;
  return cellValue === filterBool;
};

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
        minHeight: 22,
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

function AllianceNameColumnFilter({
  column,
  data,
  disabledReason,
}: {
  column: MRT_Column<RaidTarget, unknown>;
  data: string[];
  disabledReason?: string | null;
}) {
  const raw = column.getFilterValue();
  const value: string[] = Array.isArray(raw)
    ? (raw as unknown[]).map((v) => String(v)).filter((s) => s.length > 0)
    : raw == null || raw === ''
      ? []
      : [String(raw)];

  const control = (
    <Box style={{ width: '100%', maxWidth: '100%', minWidth: 0 }}>
      <MultiSelect
        size="xs"
        variant="unstyled"
        data={data}
        value={value}
        onChange={(v) => column.setFilterValue(v.length ? v : undefined)}
        placeholder="Filter by Alliance"
        searchable
        clearable
        hidePickedOptions
        maxDropdownHeight={280}
        disabled={!!disabledReason}
        styles={{
          root: { width: '100%', maxWidth: '100%', minWidth: 0 },
          wrapper: { width: '100%', maxWidth: '100%', minWidth: 0 },
          input: {
            width: '100%',
            maxWidth: '100%',
            minWidth: 0,
            border: 'none',
            background: 'transparent',
            paddingInline: 0,
          },
          pillsList: {
            maxWidth: '100%',
            maxHeight: 84,
            overflowY: 'auto',
            overflowX: 'hidden',
          },
        }}
      />
    </Box>
  );

  if (!disabledReason) {
    return control;
  }

  return (
    <Tooltip
      label={disabledReason}
      multiline
      maw={280}
      withinPortal
      events={{ hover: true, focus: true, touch: true }}
    >
      <Box component="span" style={{ display: 'block', width: '100%', maxWidth: '100%', minWidth: 0 }}>
        {control}
      </Box>
    </Tooltip>
  );
}

interface RaidsTableProps {
  data: RaidTarget[];
  /** Sorted alliance names for the column multi-select (full target list + current picks). */
  allianceSelectOptions: string[];
  /** When set, the Alliance column filter is disabled and this text is shown in a tooltip (e.g. sidebar exclude mode). */
  allianceFilterDisabledReason?: string | null;
  /** Sorted alliance positions for the column multi-select (unfiltered targets + picks). */
  positionSelectOptions: { value: string; label: string }[];
  /** Signed in with Discord: beige reminders need only this. */
  discordAuthenticated: boolean;
  /** The nation loaded on the page, for the damage calculator deep link. */
  damageAttackerNationId?: string | null;
  initialSorting?: { id: string; desc: boolean }[];
  columnVisibility: MRT_VisibilityState;
  columnOrder: MRT_ColumnOrderState;
  columnFilters: MRT_ColumnFiltersState;
  onColumnVisibilityChange: (
    updater: MRT_VisibilityState | ((prev: MRT_VisibilityState) => MRT_VisibilityState)
  ) => void;
  onColumnOrderChange: (
    updater: MRT_ColumnOrderState | ((prev: MRT_ColumnOrderState) => MRT_ColumnOrderState)
  ) => void;
  onColumnFiltersChange: Dispatch<SetStateAction<MRT_ColumnFiltersState>>;
}

export function RaidsTable({
  data,
  allianceSelectOptions,
  allianceFilterDisabledReason,
  positionSelectOptions,
  discordAuthenticated,
  damageAttackerNationId,
  initialSorting = [],
  columnVisibility,
  columnOrder,
  columnFilters,
  onColumnVisibilityChange,
  onColumnOrderChange,
  onColumnFiltersChange,
}: RaidsTableProps) {
  const queryClient = useQueryClient();
  const location = useLocation();
  const navigate = useNavigate();
  const [pagination, setPagination] = useState({
    pageIndex: 0,
    pageSize: 50,
  });
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    nation: RaidTarget;
  } | null>(null);
  const [selectedNationIds, setSelectedNationIds] = useState<Set<number>>(() => new Set());
  // Sign in and come back to this page with its filters.
  const loginUrl = getDiscordLoginUrl(internalNavPath(location.pathname, location.search));
  // Compare against the loaded nation when there is one; the calculator works without sign-in.
  const damageLink = contextMenu
    ? `/damage?${new URLSearchParams({
        ...(damageAttackerNationId ? { nation1: damageAttackerNationId } : {}),
        nation2: String(contextMenu.nation.id),
      }).toString()}`
    : '#';
  const [lastSelectedNationId, setLastSelectedNationId] = useState<number | null>(null);

  // Reminder changes made here, by nation id. Kept beside the data instead of rewriting every
  // cached target list, so a toggle doesn't hand the table a new data array (which would reset
  // its page) or rerun every filter for one cell.
  const [reminderOverrides, setReminderOverrides] = useState<ReadonlyMap<number, boolean>>(
    () => new Map()
  );
  const hasReminder = useCallback(
    (nation: RaidTarget) => reminderOverrides.get(nation.id) ?? nation.hasReminderActive,
    [reminderOverrides]
  );

  const onReminderChanged = useCallback(
    (nationId: number, active: boolean) => {
      setReminderOverrides((prev) => new Map(prev).set(nationId, active));
      void queryClient.invalidateQueries({ queryKey: REMINDERS_QUERY_KEY });
      // Other cached lists refetch next time they are shown.
      void queryClient.invalidateQueries({ queryKey: ['raids'], refetchType: 'none' });
    },
    [queryClient]
  );

  const { mutate: addReminderForNation } = useMutation({
    mutationKey: REMINDER_MUTATION_KEY,
    mutationFn: (nationId: number) => {
      if (!discordAuthenticated) return Promise.reject(new Error('Log in with Discord to use reminders'));
      return addReminder({ nationId });
    },
    onSuccess: (data, nationId) => {
      notifications.show({ title: 'Reminder Set', message: `Nation ${nationId}`, color: 'green' });
      onReminderChanged(nationId, true);

      if (data.delivery?.needsAttention) {
        // Fixed id: adding several targets in a row shows this warning once.
        const attentionToastId = 'reminder-delivery-needs-attention';
        notifications.show({
          id: attentionToastId,
          title: 'Reminder added, but it may not reach you',
          message: (
            <>
              One of your delivery methods isn't working.{' '}
              <Anchor
                href="/reminders"
                size="sm"
                onClick={(event) => {
                  event.preventDefault();
                  notifications.hide(attentionToastId);
                  navigate('/reminders');
                }}
              >
                Fix it on the Reminders page
              </Anchor>
            </>
          ),
          color: 'yellow',
          autoClose: 12_000,
        });
      } else if (data.testDm) {
        notifications.show({
          title: 'Checking your Discord DMs',
          message: 'Autolycus is sending you a test DM. Click Got it in the DM so you know reminders reach you.',
          color: 'blue',
        });
      }
    },
    onError: (error: Error) => notifications.show({ title: 'Error', message: error.message, color: 'red' }),
  });

  const { mutate: removeReminderForNation } = useMutation({
    mutationKey: REMINDER_MUTATION_KEY,
    mutationFn: (nationId: number) => {
      if (!discordAuthenticated) return Promise.reject(new Error('Log in with Discord to use reminders'));
      return removeReminder(nationId);
    },
    onSuccess: (_, nationId) => {
      notifications.show({ title: 'Reminder Removed', message: `Nation ${nationId}`, color: 'blue' });
      onReminderChanged(nationId, false);
    },
    onError: (error: Error) => notifications.show({ title: 'Error', message: error.message, color: 'red' }),
  });

  // Nations with a reminder request in flight: only their buttons wait.
  const pendingReminderNationIds = useMutationState({
    filters: { mutationKey: REMINDER_MUTATION_KEY, status: 'pending' },
    select: (mutation) => mutation.state.variables as number,
  });
  const reminderPending = useMemo(
    () => new Set(pendingReminderNationIds),
    [pendingReminderNationIds]
  );

  const toggleReminderForNation = useCallback(
    (nation: RaidTarget) => {
      if (reminderPending.has(nation.id)) return;
      if (hasReminder(nation)) removeReminderForNation(nation.id);
      else addReminderForNation(nation.id);
    },
    [addReminderForNation, removeReminderForNation, hasReminder, reminderPending]
  );

  const isInteractiveElement = useCallback((target: EventTarget | null): boolean => {
    if (!(target instanceof Element)) return false;
    return Boolean(
      target.closest(
        'a, button, input, select, textarea, [role="button"], [role="link"], [data-ignore-row-select]'
      )
    );
  }, []);

  const handleRowClick = useCallback(
    (
      event: ReactMouseEvent<HTMLTableRowElement>,
      row: MRT_Row<RaidTarget>,
      tableInstance: MRT_TableInstance<RaidTarget>
    ) => {
      if (isInteractiveElement(event.target)) return;
      const nationId = row.original.id;

      setSelectedNationIds((prev) => {
        const next = new Set(prev);
        const currentRows = tableInstance.getRowModel().rows;
        const rowIdsInView = currentRows.map((r) => r.original.id);

        if (event.shiftKey && lastSelectedNationId !== null) {
          const startIndex = rowIdsInView.indexOf(lastSelectedNationId);
          const endIndex = rowIdsInView.indexOf(nationId);
          if (startIndex !== -1 && endIndex !== -1) {
            const [from, to] = startIndex <= endIndex ? [startIndex, endIndex] : [endIndex, startIndex];
            for (let i = from; i <= to; i += 1) {
              next.add(rowIdsInView[i]);
            }
            return next;
          }
        }

        if (event.ctrlKey || event.metaKey) {
          if (next.has(nationId)) next.delete(nationId);
          else next.add(nationId);
          return next;
        }

        return new Set([nationId]);
      });

      setLastSelectedNationId(nationId);
    },
    [isInteractiveElement, lastSelectedNationId]
  );

  useEffect(() => {
    setSelectedNationIds((prev) => {
      if (prev.size === 0) return prev;
      const validIds = new Set(data.map((d) => d.id));
      return Array.from(prev).every((id) => validIds.has(id))
        ? prev
        : new Set(Array.from(prev).filter((id) => validIds.has(id)));
    });
    setLastSelectedNationId((prev) => (prev !== null && data.some((d) => d.id === prev) ? prev : null));
  }, [data]);

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

  const uniqueAlliances = allianceSelectOptions;
  const uniquePositions = positionSelectOptions;

  const uniqueColors = useMemo(() => {
    const colors = new Set(data.map((d) => d.color).filter(Boolean));
    return Array.from(colors).sort();
  }, [data]);

  const cityRange = useMemo(() => {
    const cities = data.map(d => d.numCities);
    if (!cities.length) return [0, 0];
    return [Math.min(...cities), Math.max(...cities)];
  }, [data]);

  const scoreRange = useMemo(() => {
    const scores = data.map((d) => d.score).filter((s) => Number.isFinite(s));
    if (!scores.length) return [0, 0];
    // Whole-number ends: the slider steps by 1, and fractional ends would round inward and
    // hide the highest and lowest scores.
    return [Math.floor(Math.min(...scores)), Math.ceil(Math.max(...scores))];
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
        filterFn: allianceNameMultiSelectFilterFn,
        Filter: ({ column }) => (
          <AllianceNameColumnFilter
            column={column}
            data={uniqueAlliances}
            disabledReason={allianceFilterDisabledReason}
          />
        ),
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
          const value = cell.getValue<string | null>() ?? '';
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
        accessorKey: 'score',
        header: 'Score',
        size: 90,
        mantineTableBodyCellProps: { align: 'right' },
        filterVariant: 'range-slider',
        mantineFilterRangeSliderProps: {
          min: scoreRange[0],
          max: scoreRange[1],
          step: 1,
          minRange: 0,
        },
        Cell: ({ cell }) => {
          const value = cell.getValue<number>();
          return Number.isFinite(value) ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—';
        },
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
        Cell: ({ cell }) => {
          const color = cell.getValue<string | null>() ?? '';
          return color ? (
            <Badge variant="light" color={getColorBadge(color)}>
              {color}
            </Badge>
          ) : (
            '—'
          );
        },
      },
      {
        accessorKey: 'beigeTurns',
        header: 'Beige Turns',
        size: 90,
        mantineTableBodyCellProps: { align: 'center' },
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
          discordAuthenticated ? (
            wrappedHeader('Reminder')
          ) : (
            <Tooltip
              label="Log in with Discord (in a beige row, the sidebar or the banner above) to set reminders."
              multiline
              maw={280}
              withinPortal
            >
              <Box style={{ cursor: 'help' }}>{wrappedHeader('Reminder')}</Box>
            </Tooltip>
          ),
        size: discordAuthenticated ? 138 : 176,
        enableSorting: false,
        enableColumnFilter: false,
        mantineTableBodyCellProps: {
          align: 'center',
          style: { verticalAlign: 'middle', ...MRT_RAIDS_BODY_CELL_PAD },
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
          if (!discordAuthenticated) {
            return (
              <ReminderColumnCell fullWidth>
                <Button
                  size="compact-xs"
                  variant="light"
                  radius="sm"
                  component="a"
                  href={loginUrl}
                  leftSection={<IconBrandDiscord size={12} />}
                  fullWidth
                >
                  Log in with Discord
                </Button>
              </ReminderColumnCell>
            );
          }
          const active = hasReminder(nation);
          return (
            <ReminderColumnCell>
              <Tooltip label={active ? 'Remove reminder' : 'Set reminder'}>
                <Button
                  size="compact-xs"
                  variant={active ? 'filled' : 'light'}
                  color={active ? 'green' : 'gray'}
                  radius="sm"
                  leftSection={
                    active ? <IconBell size={14} stroke={1.5} /> : <IconBellOff size={14} stroke={1.5} />
                  }
                  onClick={() => toggleReminderForNation(nation)}
                  loading={reminderPending.has(nation.id)}
                >
                  {active ? 'Remove' : 'Add'}
                </Button>
              </Tooltip>
            </ReminderColumnCell>
          );
        },
      } as MRT_ColumnDef<RaidTarget>,
      {
        // Parsed once per row (TanStack caches accessor values) instead of in every comparison.
        id: 'nationLoot',
        accessorFn: (row) => parseNumericValue(row.nationLoot),
        header: 'Beige Loot',
        size: 100,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ row }) => row.original.nationLoot,
        filterFn: minOnlyFilter,
        Filter: ({ column }) => (
          <DebouncedTextFilterInput column={column} placeholder="Min (e.g. 10k, 2m)" />
        ),
      },
      {
        accessorKey: 'daysInactive',
        header: 'Days Inactive',
        size: 105,
        mantineTableBodyCellProps: { align: 'center' },
        filterFn: minOnlyFilter,
        Filter: ({ column }) => (
          <DebouncedTextFilterInput column={column} placeholder="Min days (e.g. 7, 30)" />
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
              <Text span size="sm">
                {relative}
              </Text>
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
        Cell: ({ cell }) => formatMoney(cell.getValue<number>()),
        filterFn: minOnlyFilter,
        Filter: ({ column }) => (
          <DebouncedTextFilterInput column={column} placeholder="Min (e.g. 10k, 2m)" />
        ),
      },
      {
        accessorKey: 'netCashIncome',
        header: 'Cash Income',
        Header: () => headerWithTooltip('Cash Income', 'Net cash-only income (excludes the value of produced resources).'),
        size: 105,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => formatMoney(cell.getValue<number>()),
        filterFn: minOnlyFilter,
        Filter: ({ column }) => (
          <DebouncedTextFilterInput column={column} placeholder="Min (e.g. 10k, 2m)" />
        ),
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
        id: 'timeSinceWar',
        accessorFn: (row) => timeSinceWarDays(row.timeSinceWar),
        header: 'Days Since War',
        size: 120,
        mantineTableBodyCellProps: { align: 'center' },
        Cell: ({ row }) => String(row.original.timeSinceWar),
        filterFn: minOnlyFilter,
        Filter: NumericMinOnlyFilterInput,
      },
      // Military columns 
      {
        accessorKey: 'soldiers',
        header: 'Soldiers',
        size: 110,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => (cell.getValue<number | null>() ?? 0).toLocaleString(),
        filterFn: maxOnlyFilter,
        Filter: ({ column }) => <DebouncedTextFilterInput column={column} placeholder="Max (e.g. 500k)" />,
      },
      {
        accessorKey: 'tanks',
        header: 'Tanks',
        size: 90,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => (cell.getValue<number | null>() ?? 0).toLocaleString(),
        filterFn: maxOnlyFilter,
        Filter: ({ column }) => <DebouncedTextFilterInput column={column} placeholder="Max (e.g. 20k)" />,
      },
      {
        accessorKey: 'aircraft',
        header: 'Aircraft',
        size: 105,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: maxOnlyFilter,
        Filter: ({ column }) => <DebouncedTextFilterInput column={column} placeholder="Max (e.g. 2k)" />,
      },
      {
        accessorKey: 'ships',
        header: 'Ships',
        size: 90,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: maxOnlyFilter,
        Filter: ({ column }) => <DebouncedTextFilterInput column={column} placeholder="Max (e.g. 400)" />,
      },
      {
        accessorKey: 'missiles',
        header: 'Missiles',
        size: 105,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: maxOnlyFilter,
        Filter: ({ column }) => <DebouncedTextFilterInput column={column} placeholder="Max (e.g. 50)" />,
      },
      {
        accessorKey: 'nukes',
        header: 'Nukes',
        size: 95,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: maxOnlyFilter,
        Filter: ({ column }) => <DebouncedTextFilterInput column={column} placeholder="Max (e.g. 20)" />,
      },
      {
        accessorKey: 'groundWin',
        header: 'Ground Win %',
        size: 105, // "Ground" needs ~50px + Icon ~20px + Padding
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => winCell(cell.getValue<number | null>()),
        filterFn: minOnlyFilter,
        Filter: ({ column }) => <NumericMinOnlyFilterInput column={column} max={100} />,
      },
      {
        accessorKey: 'airWin',
        header: 'Air Win %',
        size: 100,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => winCell(cell.getValue<number | null>()),
        filterFn: minOnlyFilter,
        Filter: ({ column }) => <NumericMinOnlyFilterInput column={column} max={100} />,
      },
      {
        accessorKey: 'navalWin',
        header: 'Naval Win %',
        size: 100,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => winCell(cell.getValue<number | null>()),
        filterFn: minOnlyFilter,
        Filter: ({ column }) => <NumericMinOnlyFilterInput column={column} max={100} />,
      },
      {
        accessorKey: 'totalWin',
        header: 'Total Win %',
        size: 100,
        mantineTableBodyCellProps: { align: 'right' },
        Cell: ({ cell }) => winCell(cell.getValue<number | null>()),
        filterFn: minOnlyFilter,
        Filter: ({ column }) => <NumericMinOnlyFilterInput column={column} max={100} />,
      },

    ],
    [
      discordAuthenticated,
      loginUrl,
      hasReminder,
      reminderPending,
      toggleReminderForNation,
      uniqueAlliances,
      allianceFilterDisabledReason,
      uniquePositions,
      uniqueColors,
      cityRange,
      scoreRange,
    ]
  );

  const renderToolbarInternalActions = useCallback(
    ({ table: t }: { table: MRT_TableInstance<RaidTarget> }) => (
      <MrtTableToolbarInternalActions
        table={t}
        onExportCsv={() => downloadCsv(raidsCsvFilename(), buildRaidsCsv(t, { hasReminder }))}
      />
    ),
    [hasReminder]
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
    enableFilterMatchHighlighting: false,

    globalFilterFn: 'contains',

    initialState: {
      columnFilters,
      sorting: initialSorting,
      density: 'xs',
    },
    state: {
      pagination,
      columnVisibility,
      columnOrder,
      columnFilters,
    },
    onPaginationChange: setPagination,
    onColumnVisibilityChange,
    onColumnOrderChange,
    // The page's setter applies MRT's updater to the latest filters.
    onColumnFiltersChange,
    
    mantineTableContainerProps: {
      style: { maxHeight: '600px' },
    },
    mantineTableProps: {
      className: 'raids-table',
      style: { minWidth: '100%' },
      striped: true,
      verticalSpacing: 0,
    },
    mantineTableHeadCellProps: {
      style: {
        padding: '2px 4px',
        verticalAlign: 'bottom',
      },
    },
    mantineTableBodyCellProps: {
      fz: 'sm',
      style: { ...MRT_RAIDS_BODY_CELL_PAD },
    },
    mantineTableBodyRowProps: ({ row, table: tableInstance }) => {
      const isSelected = selectedNationIds.has(row.original.id);
      return {
        onClick: (event) => handleRowClick(event, row, tableInstance),
        onContextMenu: (event) => {
          event.preventDefault();
          setContextMenu({
            x: event.clientX,
            y: event.clientY,
            nation: row.original,
          });
        },
        className: isSelected ? 'raids-row-selected' : undefined,
        style: {
          cursor: 'pointer',
        },
      };
    },
    mantinePaperProps: {
      shadow: 'sm',
      radius: 'md',
      withBorder: true,
      px: { base: 'xs', sm: 'lg' },
    },
    mantineTopToolbarProps: {
      className: 'raids-mrt-top-toolbar',
    },
    mantineBottomToolbarProps: {
      className: 'raids-mrt-bottom-toolbar',
    },
    renderToolbarInternalActions,
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
            rel="noopener noreferrer"
            onClick={(e) => handleExternalMenuLink(e, () => setContextMenu(null))}
            onAuxClick={(e) => handleExternalMenuLink(e, () => setContextMenu(null))}
          >
            Open nation page
          </Menu.Item>
          {contextMenu && contextMenu.nation.allianceId !== '0' ? (
            <Menu.Item
              leftSection={<IconExternalLink size={16} />}
              component="a"
              href={`https://politicsandwar.com/alliance/id=${contextMenu.nation.allianceId}`}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => handleExternalMenuLink(e, () => setContextMenu(null))}
              onAuxClick={(e) => handleExternalMenuLink(e, () => setContextMenu(null))}
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
            rel="noopener noreferrer"
            onClick={(e) => handleExternalMenuLink(e, () => setContextMenu(null))}
            onAuxClick={(e) => handleExternalMenuLink(e, () => setContextMenu(null))}
          >
            Declare war
          </Menu.Item>
          <Menu.Item
            leftSection={<IconExternalLink size={16} />}
            component="a"
            href={internalNavPath('/reminders', location.search)}
            onClick={(e) =>
              handleSpaMenuAnchorClick(e, navigate, internalNavPath('/reminders', location.search), () =>
                setContextMenu(null)
              )
            }
          >
            Manage reminders
          </Menu.Item>
          <Menu.Divider />
          <Menu.Item
            leftSection={<IconChartBar size={16} />}
            component="a"
            href={damageLink}
            onClick={(e) => {
              if (!contextMenu) return;
              handleSpaMenuAnchorClick(e, navigate, damageLink, () => setContextMenu(null));
            }}
          >
            Damage calculator vs this nation
          </Menu.Item>
          <Menu.Divider />
          <Menu.Item
            leftSection={
              contextMenu && hasReminder(contextMenu.nation) ? <IconBell size={16} /> : <IconBellOff size={16} />
            }
            disabled={
              !contextMenu ||
              contextMenu.nation.beigeTurns <= 0 ||
              !discordAuthenticated ||
              reminderPending.has(contextMenu.nation.id)
            }
            onClick={() => {
              if (!contextMenu) return;
              toggleReminderForNation(contextMenu.nation);
            }}
          >
            {!discordAuthenticated
              ? 'Log in with Discord to set reminders'
              : contextMenu && hasReminder(contextMenu.nation)
                ? 'Remove beige reminder'
                : 'Add beige reminder'}
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>
      <MantineReactTable table={table} />
      <Alert icon={<IconInfoCircle size={16} />} title="Pro Tip" color="blue" variant="light">
        Hold Shift and click another header to add a secondary sort (tie-breaker); sorted headers show a small badge
        (1 = first, 2 = second). Hide or show columns, reorder them and filter columns by using the controls in the
        top-right of the table. Right-click any row for quick links (PnW pages, reminders, damage calculator) or to set
        a beige reminder. Click rows to highlight; use Ctrl/Cmd-click for multi-select and Shift-click for a range.
        Use Manage reminders for timing offsets and bulk cleanup.
      </Alert>
    </Stack>
  );
}

const REMINDER_MUTATION_KEY = ['raid-reminder'] as const;

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
