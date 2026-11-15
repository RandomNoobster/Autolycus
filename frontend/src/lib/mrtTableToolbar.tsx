/**
 * Shared Mantine React Table toolbar (Search, Filters, CSV, Columns, full screen).
 * Desktop uses text+icon Buttons; mobile uses MRT ActionIcons (useIsMobile breakpoint).
 * Both tables use a fixed compact density, so there is no density toggle.
 */

import { ActionIcon, Button, Group, Menu, Tooltip } from '@mantine/core';
import { IconDownload } from '@tabler/icons-react';
import {
  MRT_ShowHideColumnsButton,
  MRT_ShowHideColumnsMenu,
  MRT_ToggleFiltersButton,
  MRT_ToggleFullScreenButton,
  MRT_ToggleGlobalFilterButton,
  type MRT_RowData,
  type MRT_TableInstance,
} from 'mantine-react-table';
import { useIsMobile } from '@/hooks/useIsMobile';

const TOOLBAR_ICON_SZ = 18;

const CSV_TOOLTIP_ENABLED = 'Download filtered rows as CSV (includes all pages)';
const CSV_TOOLTIP_DISABLED = 'No rows match the current filters';

export type MrtTableToolbarInternalActionsProps<TData extends MRT_RowData> = {
  table: MRT_TableInstance<TData>;
  onExportCsv: () => void;
};

export function MrtTableToolbarInternalActions<TData extends MRT_RowData>({
  table,
  onExportCsv,
}: MrtTableToolbarInternalActionsProps<TData>) {
  const isMobile = useIsMobile();
  const showLabels = !isMobile;
  const canExportCsv = table.getPrePaginationRowModel().rows.length > 0;

  const {
    columnFilterDisplayMode,
    enableColumnFilters,
    enableColumnOrdering,
    enableColumnPinning,
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
    },
    localization: {
      showHideSearch,
      showHideFilters,
      showHideColumns,
      toggleFullScreen,
    },
  } = table.options;

  const {
    getState,
    refs: { searchInputRef },
    setShowGlobalFilter,
    setShowColumnFilters,
    setIsFullScreen,
  } = table;

  const toolbarLabel = {
    search: 'Search',
    filters: 'Filters',
    columns: 'Columns',
    fullscreen: 'Full screen',
  } as const;

  if (!showLabels) {
    return (
      <Group gap={4} wrap="nowrap" className="mrt-toolbar-internal-buttons">
        {enableFilters && enableGlobalFilter && !initialState?.showGlobalFilter && (
          <MRT_ToggleGlobalFilterButton key="search" table={table} />
        )}
        {enableFilters && enableColumnFilters && columnFilterDisplayMode !== 'popover' && (
          <MRT_ToggleFiltersButton key="filters" table={table} />
        )}
        {(enableHiding || enableColumnOrdering || enableColumnPinning) && (
          <MRT_ShowHideColumnsButton key="columns" table={table} />
        )}
        {enableFullScreenToggle && <MRT_ToggleFullScreenButton key="fullscreen" table={table} />}
        <Tooltip
          key="csv"
          label={canExportCsv ? CSV_TOOLTIP_ENABLED : CSV_TOOLTIP_DISABLED}
          withinPortal
        >
          <ActionIcon
            variant="subtle"
            color="gray"
            size="lg"
            radius="sm"
            disabled={!canExportCsv}
            aria-label="Download CSV"
            onClick={onExportCsv}
          >
            <IconDownload size={TOOLBAR_ICON_SZ} />
          </ActionIcon>
        </Tooltip>
      </Group>
    );
  }

  const { globalFilter, showGlobalFilter, showColumnFilters, isFullScreen } = getState();

  return (
    <Group
      gap={4}
      wrap="wrap"
      justify="flex-end"
      align="center"
      className="mrt-toolbar-internal-buttons"
    >
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
              showGlobalFilter ? (
                <IconSearchOff size={TOOLBAR_ICON_SZ} />
              ) : (
                <IconSearch size={TOOLBAR_ICON_SZ} />
              )
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
              showColumnFilters ? (
                <IconFilterOff size={TOOLBAR_ICON_SZ} />
              ) : (
                <IconFilter size={TOOLBAR_ICON_SZ} />
              )
            }
            onClick={() => setShowColumnFilters((c) => !c)}
          >
            {toolbarLabel.filters}
          </Button>
        </Tooltip>
      )}
      <Tooltip
        key="csv"
        label={canExportCsv ? CSV_TOOLTIP_ENABLED : CSV_TOOLTIP_DISABLED}
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
          onClick={onExportCsv}
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
      {enableFullScreenToggle && (
        <Tooltip key="fullscreen" label={toggleFullScreen} withinPortal>
          <Button
            variant="subtle"
            color="gray"
            size="sm"
            fw={500}
            aria-label={toggleFullScreen}
            leftSection={
              isFullScreen ? (
                <IconMinimize size={TOOLBAR_ICON_SZ} />
              ) : (
                <IconMaximize size={TOOLBAR_ICON_SZ} />
              )
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
