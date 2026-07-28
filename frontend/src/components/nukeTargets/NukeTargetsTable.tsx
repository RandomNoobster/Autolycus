import {
  useMemo,
  useState,
  useCallback,
  type MouseEvent as ReactMouseEvent,
} from 'react';
import {
  MantineReactTable,
  useMantineReactTable,
  type MRT_ColumnDef,
  type MRT_ColumnOrderState,
  type MRT_DensityState,
  type MRT_TableInstance,
  type MRT_VisibilityState,
} from 'mantine-react-table';
import {
  Anchor,
  Badge,
  Box,
  Menu,
  Stack,
  Text,
} from '@mantine/core';
import {
  IconChartBar,
  IconExternalLink,
} from '@tabler/icons-react';
import { useNavigate, type NavigateFunction } from 'react-router-dom';

import type { NukeTarget } from '@/types';
import { MrtTableToolbarInternalActions } from '@/lib/mrtTableToolbar';
import { downloadCsv } from '@/lib/raidsCsvExport';
import {
  headerWithTooltip,
  minOnlyFilter,
  MRT_RAIDS_BODY_CELL_PAD,
  NumericMinOnlyFilterInput,
  wrappedHeader,
} from '@/lib/mrtRaidsTableUi';
import { NUKE_TARGET_COLUMN_DOCS, NUKE_TARGET_COLUMN_LABELS } from '@/lib/nukeTargetsColumnDocs';

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

const formatMoney = (value: number | undefined) => {
  if (value === undefined || Number.isNaN(value)) return '—';
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(2)}B`;
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${Math.round(value).toLocaleString()}`;
};

const formatInfra = (value: number | undefined) => {
  if (value === undefined || Number.isNaN(value)) return '—';
  return Math.round(value).toLocaleString();
};

const boolBadge = (on: boolean | undefined, onLabel: string) =>
  on ? (
    <Badge size="sm" color="red" variant="light">
      {onLabel}
    </Badge>
  ) : (
    <Text size="sm" c="dimmed">
      No
    </Text>
  );

/** Soft color by defender infra-taken effect relevant to nuke/missile damage. */
function defenderWarPolicyCell(policy: string | undefined) {
  const label = (policy || '').trim();
  if (!label || label === 'None') {
    return (
      <Text size="sm" c="dimmed">
        {label || '—'}
      </Text>
    );
  }
  // Turtle: −10% infra taken (worse target). Cooler tone.
  if (label === 'Turtle') {
    return (
      <Text size="sm" c="cyan.4" fw={500}>
        {label}
      </Text>
    );
  }
  // Moneybags / Covert / Arcane: +5% infra taken (better target). Warmer tone.
  if (label === 'Moneybags' || label === 'Covert' || label === 'Arcane') {
    return (
      <Text size="sm" c="orange.4" fw={500}>
        {label}
      </Text>
    );
  }
  return (
    <Text size="sm" c="dimmed">
      {label}
    </Text>
  );
}

function buildNukeTargetsCsv(rows: NukeTarget[]): string {
  const headers = [
    'id',
    'nationName',
    'leaderName',
    'allianceName',
    'alliancePosition',
    'numCities',
    'score',
    'simNukeNet',
    'simMissileNet',
    'nukeDamage',
    'nukeDamageWithoutVds',
    'nukeNet',
    'missileDamage',
    'maxInfra',
    'avgInfra',
    'vds',
    'ironDome',
    'daysInactive',
    'defSlots',
  ];
  const lines = [
    headers.join(','),
    ...rows.map((row) =>
      headers
        .map((key) => {
          const val = (row as unknown as Record<string, unknown>)[key];
          const text = val === undefined || val === null ? '' : String(val);
          return `"${text.replace(/"/g, '""')}"`;
        })
        .join(',')
    ),
  ];
  return lines.join('\n');
}

function nukeTargetsCsvFilename(): string {
  return `nuke-targets-${new Date().toISOString().slice(0, 10)}.csv`;
}

export type NukeTargetsTableProps = {
  data: NukeTarget[];
  attackerNationId?: string;
  columnVisibility: MRT_VisibilityState;
  columnOrder: MRT_ColumnOrderState;
  density: MRT_DensityState;
  onColumnVisibilityChange: (
    updater: MRT_VisibilityState | ((prev: MRT_VisibilityState) => MRT_VisibilityState)
  ) => void;
  onColumnOrderChange: (
    updater: MRT_ColumnOrderState | ((prev: MRT_ColumnOrderState) => MRT_ColumnOrderState)
  ) => void;
  onDensityChange: (
    updater: MRT_DensityState | ((prev: MRT_DensityState) => MRT_DensityState)
  ) => void;
};

export function NukeTargetsTable({
  data,
  attackerNationId,
  columnVisibility,
  columnOrder,
  density,
  onColumnVisibilityChange,
  onColumnOrderChange,
  onDensityChange,
}: NukeTargetsTableProps) {
  const navigate = useNavigate();
  const [contextMenu, setContextMenu] = useState<{ nation: NukeTarget; x: number; y: number } | null>(
    null
  );

  const sortColumnId = 'simNukeNet';

  const [sorting, setSorting] = useState([{ id: sortColumnId, desc: true }]);

  const doc = (key: keyof typeof NUKE_TARGET_COLUMN_DOCS) =>
    headerWithTooltip(
      NUKE_TARGET_COLUMN_LABELS[key] ?? key,
      NUKE_TARGET_COLUMN_DOCS[key] ?? key
    );

  const columns = useMemo<MRT_ColumnDef<NukeTarget>[]>(
    () => [
      {
        accessorKey: 'id',
        header: NUKE_TARGET_COLUMN_LABELS.id,
        Header: () => doc('id'),
        size: 70,
        enableColumnFilter: false,
      },
      {
        accessorKey: 'nationName',
        header: NUKE_TARGET_COLUMN_LABELS.nationName,
        Header: () => doc('nationName'),
        size: 170,
        enableColumnFilter: false,
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
        header: NUKE_TARGET_COLUMN_LABELS.leaderName,
        Header: () => doc('leaderName'),
        size: 130,
        enableColumnFilter: false,
      },
      {
        accessorKey: 'allianceName',
        header: NUKE_TARGET_COLUMN_LABELS.allianceName,
        Header: () => doc('allianceName'),
        size: 140,
        enableColumnFilter: false,
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
        header: NUKE_TARGET_COLUMN_LABELS.alliancePosition,
        Header: () => doc('alliancePosition'),
        size: 110,
        enableColumnFilter: false,
        Cell: ({ cell }) => {
          const value = cell.getValue<string>() || '';
          return value === 'NOALLIANCE' || value === 'Unknown' || !value
            ? 'None'
            : value.toLowerCase();
        },
      },
      {
        accessorKey: 'numCities',
        header: NUKE_TARGET_COLUMN_LABELS.numCities,
        Header: () => doc('numCities'),
        size: 90,
        filterFn: minOnlyFilter,
        Filter: NumericMinOnlyFilterInput,
      },
      {
        accessorKey: 'score',
        header: NUKE_TARGET_COLUMN_LABELS.score,
        Header: () => doc('score'),
        size: 90,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: minOnlyFilter,
        Filter: NumericMinOnlyFilterInput,
        Cell: ({ cell }) => Number(cell.getValue<number>()).toFixed(2),
      },
      {
        accessorKey: 'simNukeNet',
        header: NUKE_TARGET_COLUMN_LABELS.simNukeNet,
        Header: () => doc('simNukeNet'),
        size: 138,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: minOnlyFilter,
        Filter: NumericMinOnlyFilterInput,
        Cell: ({ cell }) => formatMoney(cell.getValue<number>()),
      },
      {
        accessorKey: 'simMissileNet',
        header: NUKE_TARGET_COLUMN_LABELS.simMissileNet,
        Header: () => doc('simMissileNet'),
        size: 138,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: minOnlyFilter,
        Filter: NumericMinOnlyFilterInput,
        Cell: ({ cell }) => formatMoney(cell.getValue<number>()),
      },
      {
        accessorKey: 'nukeDamage',
        header: NUKE_TARGET_COLUMN_LABELS.nukeDamage,
        Header: () => doc('nukeDamage'),
        size: 128,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: minOnlyFilter,
        Filter: NumericMinOnlyFilterInput,
        Cell: ({ cell }) => formatMoney(cell.getValue<number>()),
      },
      {
        accessorKey: 'nukeDamageWithoutVds',
        header: NUKE_TARGET_COLUMN_LABELS.nukeDamageWithoutVds,
        Header: () => doc('nukeDamageWithoutVds'),
        size: 150,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: minOnlyFilter,
        Filter: NumericMinOnlyFilterInput,
        Cell: ({ cell }) => formatMoney(cell.getValue<number>()),
      },
      {
        accessorKey: 'nukeNet',
        header: NUKE_TARGET_COLUMN_LABELS.nukeNet,
        Header: () => doc('nukeNet'),
        size: 138,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: minOnlyFilter,
        Filter: NumericMinOnlyFilterInput,
        Cell: ({ cell }) => formatMoney(cell.getValue<number>()),
      },
      {
        accessorKey: 'missileDamage',
        header: NUKE_TARGET_COLUMN_LABELS.missileDamage,
        Header: () => doc('missileDamage'),
        size: 132,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: minOnlyFilter,
        Filter: NumericMinOnlyFilterInput,
        Cell: ({ cell }) => formatMoney(cell.getValue<number>()),
      },
      {
        accessorKey: 'missileDamageWithoutIronDome',
        header: NUKE_TARGET_COLUMN_LABELS.missileDamageWithoutIronDome,
        Header: () => doc('missileDamageWithoutIronDome'),
        size: 158,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: minOnlyFilter,
        Filter: NumericMinOnlyFilterInput,
        Cell: ({ cell }) => formatMoney(cell.getValue<number>()),
      },
      {
        accessorKey: 'nukeInfraLost',
        header: NUKE_TARGET_COLUMN_LABELS.nukeInfraLost,
        Header: () => doc('nukeInfraLost'),
        size: 144,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: minOnlyFilter,
        Filter: NumericMinOnlyFilterInput,
        Cell: ({ cell }) => formatInfra(cell.getValue<number>()),
      },
      {
        accessorKey: 'maxInfra',
        header: NUKE_TARGET_COLUMN_LABELS.maxInfra,
        Header: () => doc('maxInfra'),
        size: 152,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: minOnlyFilter,
        Filter: NumericMinOnlyFilterInput,
        Cell: ({ cell }) => formatInfra(cell.getValue<number>()),
      },
      {
        accessorKey: 'avgInfra',
        header: NUKE_TARGET_COLUMN_LABELS.avgInfra,
        Header: () => doc('avgInfra'),
        size: 148,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: minOnlyFilter,
        Filter: NumericMinOnlyFilterInput,
        Cell: ({ cell }) => formatInfra(cell.getValue<number>()),
      },
      {
        accessorKey: 'vds',
        header: NUKE_TARGET_COLUMN_LABELS.vds,
        Header: () => doc('vds'),
        size: 82,
        enableColumnFilter: false,
        mantineTableBodyCellProps: { align: 'center' },
        Cell: ({ row }) => boolBadge(row.original.vds, 'VDS'),
      },
      {
        accessorKey: 'ironDome',
        header: NUKE_TARGET_COLUMN_LABELS.ironDome,
        Header: () => doc('ironDome'),
        size: 98,
        enableColumnFilter: false,
        mantineTableBodyCellProps: { align: 'center' },
        Cell: ({ row }) => boolBadge(row.original.ironDome, 'Dome'),
      },
      {
        accessorKey: 'falloutShelter',
        header: NUKE_TARGET_COLUMN_LABELS.falloutShelter,
        Header: () => doc('falloutShelter'),
        size: 108,
        enableColumnFilter: false,
        mantineTableBodyCellProps: { align: 'center' },
        Cell: ({ row }) => boolBadge(row.original.falloutShelter, 'Shelter'),
      },
      {
        accessorKey: 'defenderWarPolicy',
        header: NUKE_TARGET_COLUMN_LABELS.defenderWarPolicy,
        Header: () => doc('defenderWarPolicy'),
        size: 132,
        Cell: ({ row }) => defenderWarPolicyCell(row.original.defenderWarPolicy),
      },
      {
        accessorKey: 'daysInactive',
        header: NUKE_TARGET_COLUMN_LABELS.daysInactive,
        Header: () => doc('daysInactive'),
        size: 108,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: minOnlyFilter,
        Filter: NumericMinOnlyFilterInput,
      },
      {
        accessorKey: 'defSlots',
        header: NUKE_TARGET_COLUMN_LABELS.defSlots,
        Header: () => doc('defSlots'),
        size: 122,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: minOnlyFilter,
        Filter: NumericMinOnlyFilterInput,
      },
      {
        accessorKey: 'beigeTurns',
        header: NUKE_TARGET_COLUMN_LABELS.beigeTurns,
        Header: () => doc('beigeTurns'),
        size: 96,
        mantineTableBodyCellProps: { align: 'right' },
        filterFn: minOnlyFilter,
        Filter: NumericMinOnlyFilterInput,
      },
      {
        accessorKey: 'simNukeShots',
        header: NUKE_TARGET_COLUMN_LABELS.simNukeShots,
        Header: () => doc('simNukeShots'),
        size: 108,
        mantineTableBodyCellProps: { align: 'right' },
        enableColumnFilter: false,
      },
      {
        accessorKey: 'simMissileShots',
        header: NUKE_TARGET_COLUMN_LABELS.simMissileShots,
        Header: () => doc('simMissileShots'),
        size: 116,
        mantineTableBodyCellProps: { align: 'right' },
        enableColumnFilter: false,
      },
    ],
    []
  );

  const renderToolbarInternalActions = useCallback(
    ({ table: t }: { table: MRT_TableInstance<NukeTarget> }) => (
      <MrtTableToolbarInternalActions
        table={t}
        onExportCsv={() =>
          downloadCsv(
            nukeTargetsCsvFilename(),
            buildNukeTargetsCsv(t.getPrePaginationRowModel().rows.map((r) => r.original))
          )
        }
      />
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
    globalFilterFn: 'contains',
    filterFns: { minOnly: minOnlyFilter },
    initialState: {
      density: 'xs',
      sorting: [{ id: sortColumnId, desc: true }],
      pagination: { pageSize: 25, pageIndex: 0 },
    },
    state: {
      sorting,
      columnVisibility,
      columnOrder,
      density,
    },
    onSortingChange: setSorting,
    onColumnVisibilityChange,
    onColumnOrderChange,
    onDensityChange,
    mantineTableContainerProps: { style: { maxHeight: 'min(70vh, 720px)' } },
    mantineTableProps: {
      className: 'raids-table',
      style: { minWidth: '100%' },
      striped: true,
      verticalSpacing: 0,
    },
    mantineTableHeadCellProps: {
      style: { padding: '2px 4px', verticalAlign: 'bottom' },
    },
    mantineTableBodyCellProps: {
      fz: 'sm',
      style: { ...MRT_RAIDS_BODY_CELL_PAD },
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
      style: { cursor: 'context-menu' },
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
            >
              Open alliance page
            </Menu.Item>
          ) : null}
          <Menu.Item
            leftSection={<IconExternalLink size={16} />}
            component="a"
            href={
              contextMenu
                ? `https://politicsandwar.com/nation/war/declare/id=${contextMenu.nation.id}`
                : '#'
            }
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => handleExternalMenuLinkClick(e, () => setContextMenu(null))}
          >
            Declare war (choose Attrition)
          </Menu.Item>
          {attackerNationId && contextMenu ? (
            <Menu.Item
              leftSection={<IconChartBar size={16} />}
              component="a"
              href={`/damage?nation1=${encodeURIComponent(attackerNationId)}&nation2=${encodeURIComponent(
                String(contextMenu.nation.id)
              )}`}
              onClick={(e) => {
                const to = `/damage?nation1=${encodeURIComponent(attackerNationId)}&nation2=${encodeURIComponent(
                  String(contextMenu.nation.id)
                )}`;
                handleSpaMenuAnchorClick(e, navigate, to, () => setContextMenu(null));
              }}
            >
              Damage calculator vs this nation
            </Menu.Item>
          ) : null}
        </Menu.Dropdown>
      </Menu>
      <MantineReactTable table={table} />
    </Stack>
  );
}
