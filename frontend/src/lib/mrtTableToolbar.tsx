/**
 * Shared Mantine React Table toolbar (Search, Filters, CSV, Columns, density, full screen).
 * Desktop uses text+icon Buttons; mobile uses MRT ActionIcons (breakpoint: 48em).
 */

import { ActionIcon, Button, Group, Menu, Tooltip } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { IconDownload } from '@tabler/icons-react';
import {
  MRT_ShowHideColumnsButton,
  MRT_ShowHideColumnsMenu,
  MRT_ToggleDensePaddingButton,
  MRT_ToggleFiltersButton,
  MRT_ToggleFullScreenButton,
  MRT_ToggleGlobalFilterButton,
  type MRT_DensityState,
  type MRT_TableInstance,
} from 'mantine-react-table';

const DENSITY_NEXT: Record<MRT_DensityState, MRT_DensityState> = {
  md: 'xs',
  xl: 'md',
  xs: 'xl',
};

const TOOLBAR_ICON_SZ = 18;

const CSV_TOOLTIP_ENABLED = 'Download filtered rows as CSV (includes all pages)';
const CSV_TOOLTIP_DISABLED = 'No rows match the current filters';

export type MrtTableToolbarInternalActionsProps<TData extends Record<string, any>> = {
  table: MRT_TableInstance<TData>;
  onExportCsv: () => void;
};

export function MrtTableToolbarInternalActions<TData extends Record<string, any>>({
  table,
  onExportCsv,
}: MrtTableToolbarInternalActionsProps<TData>) {
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
        {enableDensityToggle && <MRT_ToggleDensePaddingButton key="density" table={table} />}
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
