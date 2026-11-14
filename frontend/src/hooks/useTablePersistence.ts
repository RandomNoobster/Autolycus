/**
 * useTablePersistence Hook
 *
 * Persists Mantine React Table preferences in localStorage: column visibility, column order
 * and density. Only what the user changed is stored, so later changes to a table's defaults
 * (new columns, columns made visible) still reach returning users.
 */

import { useCallback, useEffect, useState } from 'react';
import type {
  MRT_ColumnOrderState,
  MRT_DensityState,
  MRT_Updater,
  MRT_VisibilityState,
} from 'mantine-react-table';

export interface TablePersistenceDefaults {
  columnVisibility: MRT_VisibilityState;
  columnOrder: MRT_ColumnOrderState;
  density: MRT_DensityState;
}

type TablePreferences = TablePersistenceDefaults;

export interface TablePersistenceOptions {
  /**
   * Columns that older versions hid by default. Version 1 storage saved the whole state on
   * the first visit, so a stored `false` for these most likely just froze the old default.
   */
  legacyHiddenByDefault?: readonly string[];
}

const STORAGE_VERSION = 2;
/** MRT's trailing display column; it can't be dragged, so it is always last. */
const SPACER_COLUMN_ID = 'mrt-row-spacer';
const DENSITIES: readonly MRT_DensityState[] = ['xs', 'md', 'xl'];

/** What localStorage holds (version 2): only the user's changes from the defaults. */
interface StoredPreferences {
  v: typeof STORAGE_VERSION;
  columnVisibility?: MRT_VisibilityState;
  columnOrder?: MRT_ColumnOrderState;
  density?: MRT_DensityState;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function sameOrder(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((id, index) => id === b[index]);
}

/**
 * The stored order with unknown ids dropped and missing ones inserted after their default
 * predecessor. Ids stored after the spacer were appended by the version 1 merge, not placed
 * by the user, so they get their default position back.
 */
function mergeColumnOrder(
  defaultOrder: MRT_ColumnOrderState,
  storedOrder: unknown
): MRT_ColumnOrderState {
  if (!Array.isArray(storedOrder) || storedOrder.length === 0) return [...defaultOrder];
  const known = new Set(defaultOrder);
  const spacerAt = storedOrder.indexOf(SPACER_COLUMN_ID);
  const placed = spacerAt >= 0 ? storedOrder.slice(0, spacerAt + 1) : storedOrder;
  const out: string[] = [];
  for (const id of placed) {
    if (typeof id === 'string' && known.has(id) && !out.includes(id)) out.push(id);
  }
  defaultOrder.forEach((id, index) => {
    if (out.includes(id)) return;
    const predecessor = defaultOrder
      .slice(0, index)
      .reverse()
      .find((prev) => out.includes(prev));
    out.splice(predecessor === undefined ? 0 : out.indexOf(predecessor) + 1, 0, id);
  });
  return out;
}

function loadPreferences(
  key: string,
  defaults: TablePersistenceDefaults,
  legacyHiddenByDefault: readonly string[]
): TablePreferences {
  let stored: unknown = null;
  try {
    const raw = localStorage.getItem(key);
    stored = raw ? JSON.parse(raw) : null;
  } catch (error) {
    console.warn(`Failed to load table preferences for ${key}:`, error);
  }
  if (!isPlainObject(stored)) {
    return {
      columnVisibility: { ...defaults.columnVisibility },
      columnOrder: [...defaults.columnOrder],
      density: defaults.density,
    };
  }

  const visibility: MRT_VisibilityState = {};
  if (isPlainObject(stored.columnVisibility)) {
    for (const [id, visible] of Object.entries(stored.columnVisibility)) {
      if (typeof visible === 'boolean') visibility[id] = visible;
    }
  }
  if (stored.v !== STORAGE_VERSION) {
    for (const id of legacyHiddenByDefault) {
      if (visibility[id] === false && defaults.columnVisibility[id] !== false) delete visibility[id];
    }
  }

  return {
    columnVisibility: { ...defaults.columnVisibility, ...visibility },
    columnOrder: mergeColumnOrder(defaults.columnOrder, stored.columnOrder),
    density: DENSITIES.includes(stored.density as MRT_DensityState)
      ? (stored.density as MRT_DensityState)
      : defaults.density,
  };
}

function savePreferences(
  key: string,
  preferences: TablePreferences,
  defaults: TablePersistenceDefaults
): void {
  const columnVisibility = Object.fromEntries(
    Object.entries(preferences.columnVisibility).filter(
      ([id, visible]) => visible !== (defaults.columnVisibility[id] ?? true)
    )
  );
  const changes: StoredPreferences = {
    v: STORAGE_VERSION,
    ...(Object.keys(columnVisibility).length > 0 ? { columnVisibility } : {}),
    ...(sameOrder(preferences.columnOrder, defaults.columnOrder)
      ? {}
      : { columnOrder: preferences.columnOrder }),
    ...(preferences.density !== defaults.density ? { density: preferences.density } : {}),
  };
  try {
    if (Object.keys(changes).length === 1) {
      // Back to the defaults: nothing worth keeping.
      localStorage.removeItem(key);
    } else {
      localStorage.setItem(key, JSON.stringify(changes));
    }
  } catch (error) {
    console.warn(`Failed to save table preferences for ${key}:`, error);
  }
}

function applyUpdater<T>(updater: MRT_Updater<T>, previous: T): T {
  return typeof updater === 'function' ? (updater as (old: T) => T)(previous) : updater;
}

interface PersistedState {
  key: string;
  preferences: TablePreferences;
  /** Set by the user's changes; loading never writes storage. */
  changed: boolean;
}

/**
 * Hook for persisting table preferences.
 *
 * @param tableId - Unique identifier for the table (e.g., 'raids')
 * @param defaults - App defaults; merged with the user's stored changes
 * @param options - See TablePersistenceOptions
 * @returns State values and setters for table preferences
 */
export function useTablePersistence(
  tableId: string,
  defaults: TablePersistenceDefaults,
  options: TablePersistenceOptions = {}
) {
  const storageKey = `autolycus-table-${tableId}`;
  const legacyHidden = options.legacyHiddenByDefault ?? [];

  const [state, setState] = useState<PersistedState>(() => ({
    key: storageKey,
    preferences: loadPreferences(storageKey, defaults, legacyHidden),
    changed: false,
  }));

  // A different table on the same mounted component (e.g. a new damage matchup): load its
  // own preferences instead of writing this table's over them.
  let current = state;
  if (state.key !== storageKey) {
    current = {
      key: storageKey,
      preferences: loadPreferences(storageKey, defaults, legacyHidden),
      changed: false,
    };
    setState(current);
  }

  useEffect(() => {
    if (state.changed) savePreferences(state.key, state.preferences, defaults);
    // `defaults` is constant per table; saving only follows the user's changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  const update = useCallback(
    <K extends keyof TablePreferences>(field: K, updater: MRT_Updater<TablePreferences[K]>) => {
      setState((prev) => ({
        ...prev,
        changed: true,
        preferences: {
          ...prev.preferences,
          [field]: applyUpdater(updater, prev.preferences[field]),
        },
      }));
    },
    []
  );

  const setColumnVisibility = useCallback(
    (updater: MRT_Updater<MRT_VisibilityState>) => update('columnVisibility', updater),
    [update]
  );
  const setColumnOrder = useCallback(
    (updater: MRT_Updater<MRT_ColumnOrderState>) => update('columnOrder', updater),
    [update]
  );
  const setDensity = useCallback(
    (updater: MRT_Updater<MRT_DensityState>) => update('density', updater),
    [update]
  );

  return {
    columnVisibility: current.preferences.columnVisibility,
    columnOrder: current.preferences.columnOrder,
    density: current.preferences.density,
    setColumnVisibility,
    setColumnOrder,
    setDensity,
  };
}
