import {
  useMemo,
  useCallback,
  useState,
  useEffect,
  useRef,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from 'react';
import {
  MantineReactTable,
  useMantineReactTable,
  MRT_ShowHideColumnsButton,
  MRT_ShowHideColumnsMenu,
  MRT_ToggleDensePaddingButton,
  MRT_ToggleFiltersButton,
  MRT_ToggleFullScreenButton,
  MRT_ToggleGlobalFilterButton,
  type MRT_ColumnDef,
  type MRT_Row,
  type MRT_ColumnFiltersState,
  type MRT_ColumnOrderState,
  type MRT_DensityState,
  type MRT_VisibilityState,
  type MRT_TableInstance,
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
import { useDebouncedValue, useMediaQuery } from '@mantine/hooks';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  IconBell,
  IconBellOff,
  IconBrandDiscord,
  IconChartBar,
  IconDownload,
  IconExternalLink,
  IconInfoCircle,
} from '@tabler/icons-react';
import { useLocation, useNavigate, type NavigateFunction } from 'react-router-dom';

import type { RaidTarget } from '@/types';
import { addReminder, removeReminder } from '@/api';
import { getDiscordLoginUrl } from '@/api/auth';
import { internalNavPath } from '@/lib/internalNavPath';
import { parseNumericValue } from '@/lib/raidFilterParsing';
import { buildRaidsCsv, downloadCsv, raidsCsvFilename } from '@/lib/raidsCsvExport';

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
function handleExternalMenuLinkClick(
  e: ReactMouseEvent<HTMLAnchorElement>,
  after: () => void
) {
  const raw = e.currentTarget.getAttribute('href');
  if (!raw || raw === '#' || !raw.startsWith('http')) return;
  e.preventDefault();
  window.open(raw, '_blank', 'noopener,noreferrer');
  after();
}

function handleExternalMenuLinkAuxClick(
  e: ReactMouseEvent<HTMLAnchorElement>,
  after: () => void
) {
  if (e.button !== 1) return;
  const raw = e.currentTarget.getAttribute('href');
  if (!raw || raw === '#' || !raw.startsWith('http')) return;
  e.preventDefault();
  window.open(raw, '_blank', 'noopener,noreferrer');
  after();
}

/** Body cell padding for raids table (Reminder column must repeat these — MRT merges props shallowly). */
const RAIDS_BODY_CELL_PAD = {
  paddingTop: 2,
  paddingBottom: 2,
  paddingLeft: 6,
  paddingRight: 6,
} as const;

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


const DENSITY_NEXT: Record<MRT_DensityState, MRT_DensityState> = {
  md: 'xs',
  xl: 'md',
  xs: 'xl',
};

const TOOLBAR_ICON_SZ = 18;

/** Same controls as MRT's default toolbar; desktop uses text+icon as one Button; mobile keeps MRT ActionIcons (App breakpoint: 48em). */
function RaidsTableToolbarInternalActions({ table }: { table: MRT_TableInstance<RaidTarget> }) {
  const isMobile = useMediaQuery('(max-width: 48em)', false, {
    getInitialValueInEffect: false,
  });
  const showLabels = !isMobile;
  const canExportCsv = table.getPrePaginationRowModel().rows.length > 0;

  const {
    columnFilterDisplayMode,
    enableColumnFilters,
    enableColumnOrdering,
    enableColumnPinning,
    enableDensityToggle,
    enableFilters,
    enableFullScreenToggle,
    enableGlobalFilter,
    enableHiding,
    initialState,
    icons: {
      IconSearch,
      IconSearchOff,
      IconFilter,
      IconFilterOff,
      IconColumns,
      IconMaximize,
      IconMinimize,
      IconBaselineDensityLarge,
      IconBaselineDensityMedium,
      IconBaselineDensitySmall,
    },
    localization: {
      showHideSearch,
      showHideFilters,
      showHideColumns,
      toggleFullScreen,
      toggleDensity,
    },
  } = table.options;

  const {
    getState,
    refs: { searchInputRef },
    setShowGlobalFilter,
    setShowColumnFilters,
    setIsFullScreen,
    setDensity,
  } = table;

  const toolbarLabel = {
    search: 'Search',
    filters: 'Filters',
    columns: 'Columns',
    density: toggleDensity,
    fullscreen: 'Full screen',
  } as const;

  if (!showLabels) {
    return (
      <>
        {enableFilters &&
          enableGlobalFilter &&
          !initialState?.showGlobalFilter && (
            <MRT_ToggleGlobalFilterButton key="search" table={table} />
          )}
        {enableFilters &&
          enableColumnFilters &&
          columnFilterDisplayMode !== 'popover' && (
            <MRT_ToggleFiltersButton key="filters" table={table} />
          )}
        {(enableHiding || enableColumnOrdering || enableColumnPinning) && (
          <MRT_ShowHideColumnsButton key="columns" table={table} />
        )}
        {enableDensityToggle && <MRT_ToggleDensePaddingButton key="density" table={table} />}
        {enableFullScreenToggle && <MRT_ToggleFullScreenButton key="fullscreen" table={table} />}
        <Tooltip
          key="csv"
          label={
            canExportCsv
              ? 'Download filtered rows as CSV (includes all pages)'
              : 'No rows match the current filters'
          }
          withinPortal
        >
          <ActionIcon
            variant="subtle"
            color="gray"
            size="lg"
            radius="sm"
            disabled={!canExportCsv}
            aria-label="Download CSV"
            onClick={() => downloadCsv(raidsCsvFilename(), buildRaidsCsv(table))}
          >
            <IconDownload size={TOOLBAR_ICON_SZ} />
          </ActionIcon>
        </Tooltip>
      </>
    );
  }

  const { globalFilter, showGlobalFilter, showColumnFilters, isFullScreen, density } = getState();

  const densityIcon =
    density === 'xs' ? (
      <IconBaselineDensitySmall size={TOOLBAR_ICON_SZ} />
    ) : density === 'md' ? (
      <IconBaselineDensityMedium size={TOOLBAR_ICON_SZ} />
    ) : (
      <IconBaselineDensityLarge size={TOOLBAR_ICON_SZ} />
    );

  return (
    <Group gap={4} wrap="wrap" justify="flex-end" align="center">
      {enableFilters && enableGlobalFilter && !initialState?.showGlobalFilter && (
        <Tooltip key="search" label={showHideSearch} withinPortal>
          <Button
            variant="subtle"
            color="gray"
            size="sm"
            fw={500}
            disabled={!!globalFilter}
            aria-label={showHideSearch}
            leftSection={
              showGlobalFilter ? <IconSearchOff size={TOOLBAR_ICON_SZ} /> : <IconSearch size={TOOLBAR_ICON_SZ} />
            }
            onClick={() => {
              setShowGlobalFilter(!showGlobalFilter);
              setTimeout(() => searchInputRef.current?.focus(), 100);
            }}
          >
            {toolbarLabel.search}
          </Button>
        </Tooltip>
      )}
      {enableFilters && enableColumnFilters && columnFilterDisplayMode !== 'popover' && (
        <Tooltip key="filters" label={showHideFilters} withinPortal>
          <Button
            variant="subtle"
            color="gray"
            size="sm"
            fw={500}
            aria-label={showHideFilters}
            leftSection={
              showColumnFilters ? <IconFilterOff size={TOOLBAR_ICON_SZ} /> : <IconFilter size={TOOLBAR_ICON_SZ} />
            }
            onClick={() => setShowColumnFilters((c) => !c)}
          >
            {toolbarLabel.filters}
          </Button>
        </Tooltip>
      )}
      <Tooltip
        key="csv"
        label={
          canExportCsv
            ? 'Download filtered rows as CSV (includes all pages)'
            : 'No rows match the current filters'
        }
        withinPortal
      >
        <Button
          variant="subtle"
          color="gray"
          size="sm"
          fw={500}
          disabled={!canExportCsv}
          aria-label="Download CSV"
          leftSection={<IconDownload size={TOOLBAR_ICON_SZ} />}
          onClick={() => downloadCsv(raidsCsvFilename(), buildRaidsCsv(table))}
        >
          CSV
        </Button>
      </Tooltip>
      {(enableHiding || enableColumnOrdering || enableColumnPinning) && (
        <Menu key="columns" closeOnItemClick={false} withinPortal>
          <Tooltip label={showHideColumns} withinPortal>
            <Menu.Target>
              <Button
                variant="subtle"
                color="gray"
                size="sm"
                fw={500}
                aria-label={showHideColumns}
                leftSection={<IconColumns size={TOOLBAR_ICON_SZ} />}
              >
                {toolbarLabel.columns}
              </Button>
            </Menu.Target>
          </Tooltip>
          <MRT_ShowHideColumnsMenu table={table} />
        </Menu>
      )}
      {enableDensityToggle && (
        <Tooltip key="density" label={toggleDensity} withinPortal>
          <Button
            variant="subtle"
            color="gray"
            size="sm"
            fw={500}
            aria-label={toggleDensity}
            leftSection={densityIcon}
            onClick={() => setDensity((d) => DENSITY_NEXT[d])}
          >
            {toolbarLabel.density}
          </Button>
        </Tooltip>
      )}
      {enableFullScreenToggle && (
        <Tooltip key="fullscreen" label={toggleFullScreen} withinPortal>
          <Button
            variant="subtle"
            color="gray"
            size="sm"
            fw={500}
            aria-label={toggleFullScreen}
            leftSection={
              isFullScreen ? <IconMinimize size={TOOLBAR_ICON_SZ} /> : <IconMaximize size={TOOLBAR_ICON_SZ} />
            }
            onClick={() => setIsFullScreen((v) => !v)}
          >
            {toolbarLabel.fullscreen}
          </Button>
        </Tooltip>
      )}
    </Group>
  );
}

interface RaidsTableProps {
  data: RaidTarget[];
  /** Alliance names for the column multi-select (from parent: full target list + current picks). Keeps options when filtered rows are empty. */
  allianceSelectOptions?: string[];
  /** Alliance positions for the column multi-select (from parent: unfiltered targets + picks). Keeps all roles visible while a position filter is active. */
  positionSelectOptions?: { value: string; label: string }[];
  discordAuthenticated: boolean;
  discordLinked: boolean;
  /** When linked, your nation ID used for raids (for damage deep-link vs context row). */
  damageAttackerNationId?: string | null;
  /** Opens the Verify Nation modal (same flow as banner / sidebar Link Nation). */
  onOpenVerifyNationModal: () => void;
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
  damageAttackerNationId,
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
          discordLinked ? (
            wrappedHeader('Reminder')
          ) : (
            <Tooltip
              label={
                discordAuthenticated
                  ? 'Link your PnW nation via Link nation in each row, the Reminder setup banner above the table, or the sidebar.'
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
          !discordLinked && discordAuthenticated ? 128 : !discordLinked ? 176 : 138,
        enableSorting: false,
        enableColumnFilter: false,
        mantineTableBodyCellProps: {
          align: 'center',
          style: { verticalAlign: 'middle', ...RAIDS_BODY_CELL_PAD },
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
                    size="compact-xs"
                    variant="light"
                    radius="sm"
                    component="a"
                    href={getDiscordLoginUrl('/raids')}
                    leftSection={<IconBrandDiscord size={12} />}
                    fullWidth
                  >
                    Log in with Discord
                  </Button>
                </ReminderColumnCell>
              );
            }
            return (
              <ReminderColumnCell fullWidth>
                <Button
                  size="compact-xs"
                  variant="light"
                  radius="sm"
                  fullWidth
                  onClick={() => onOpenVerifyNationModal()}
                >
                  Link nation
                </Button>
              </ReminderColumnCell>
            );
          }
          return (
            <ReminderColumnCell>
              <Tooltip label={nation.hasReminderActive ? 'Remove reminder' : 'Set reminder'}>
                <Button
                  size="compact-xs"
                  variant={nation.hasReminderActive ? 'filled' : 'light'}
                  color={nation.hasReminderActive ? 'green' : 'gray'}
                  radius="sm"
                  leftSection={
                    nation.hasReminderActive ? (
                      <IconBell size={14} stroke={1.5} />
                    ) : (
                      <IconBellOff size={14} stroke={1.5} />
                    )
                  }
                  onClick={() => handleReminderToggle(row)}
                  loading={addReminderMutation.isPending || removeReminderMutation.isPending}
                >
                  {nation.hasReminderActive ? 'Remove' : 'Add'}
                </Button>
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
        sortingFn: (rowA, rowB, columnId) => {
          const a = parseNumericValue(rowA.getValue<string>(columnId));
          const b = parseNumericValue(rowB.getValue<string>(columnId));
          if (a === b) return 0;
          return a > b ? 1 : -1;
        },
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

  const renderToolbarInternalActions = useCallback(
    ({ table: t }: { table: MRT_TableInstance<RaidTarget> }) => (
      <RaidsTableToolbarInternalActions table={t} />
    ),
    []
  );

  const table = useMantineReactTable({
    columns,
    data,
    autoResetPageIndex: false,
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

    filterFns: {
      minOnly: minOnlyFilter,
      maxOnly: maxOnlyFilter,
      range: rangeFilter,
    },

    globalFilterFn: 'contains',

    initialState: {
      columnFilters,
      sorting: initialSorting,
      density,
    },
    state: {
      pagination,
      columnVisibility,
      columnOrder,
      density,
      columnFilters,
    },
    onPaginationChange: setPagination,
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
      style: { ...RAIDS_BODY_CELL_PAD },
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
    mantineTopToolbarProps: {
      className: 'raids-mrt-top-toolbar',
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
            onClick={(e) => handleExternalMenuLinkClick(e, () => setContextMenu(null))}
            onAuxClick={(e) => handleExternalMenuLinkAuxClick(e, () => setContextMenu(null))}
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
              onClick={(e) => handleExternalMenuLinkClick(e, () => setContextMenu(null))}
              onAuxClick={(e) => handleExternalMenuLinkAuxClick(e, () => setContextMenu(null))}
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
            onClick={(e) => handleExternalMenuLinkClick(e, () => setContextMenu(null))}
            onAuxClick={(e) => handleExternalMenuLinkAuxClick(e, () => setContextMenu(null))}
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
          {discordLinked && damageAttackerNationId ? (
            <Menu.Item
              leftSection={<IconChartBar size={16} />}
              component="a"
              href={
                contextMenu
                  ? `/damage?nation1=${encodeURIComponent(damageAttackerNationId)}&nation2=${encodeURIComponent(
                      String(contextMenu.nation.id)
                    )}`
                  : '#'
              }
              onClick={(e) => {
                if (!contextMenu) return;
                const to = `/damage?nation1=${encodeURIComponent(damageAttackerNationId)}&nation2=${encodeURIComponent(
                  String(contextMenu.nation.id)
                )}`;
                handleSpaMenuAnchorClick(e, navigate, to, () => setContextMenu(null));
              }}
            >
              Damage calculator vs this nation
            </Menu.Item>
          ) : (
            <>
              <Menu.Label>
                <Text size="xs" c="dimmed" lh={1.35}>
                  Compare war damage on the calculator — link your nation there for saved scenarios.
                </Text>
              </Menu.Label>
              <Menu.Item
                leftSection={<IconChartBar size={16} />}
                component="a"
                href={internalNavPath('/damage', location.search)}
                onClick={(e) =>
                  handleSpaMenuAnchorClick(
                    e,
                    navigate,
                    internalNavPath('/damage', location.search),
                    () => setContextMenu(null)
                  )
                }
              >
                Open damage calculator
              </Menu.Item>
            </>
          )}
          <Menu.Divider />
          <Menu.Item
            leftSection={
              contextMenu?.nation.hasReminderActive ? <IconBell size={16} /> : <IconBellOff size={16} />
            }
            disabled={(() => {
              if (!contextMenu || contextMenu.nation.beigeTurns <= 0) return true;
              if (discordLinked) return false;
              if (discordAuthenticated) return false;
              return true;
            })()}
            onClick={() => {
              if (!contextMenu) return;
              const nation = contextMenu.nation;
              if (nation.beigeTurns <= 0) return;
              if (!discordLinked && discordAuthenticated) {
                setContextMenu(null);
                onOpenVerifyNationModal();
                return;
              }
              if (discordLinked) toggleReminderForNation(nation);
            }}
          >
            {!discordLinked && discordAuthenticated && contextMenu && contextMenu.nation.beigeTurns > 0
              ? 'Link nation to set reminders'
              : contextMenu?.nation.hasReminderActive
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
        a beige reminder. Use Manage reminders for timing offsets and bulk cleanup.
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