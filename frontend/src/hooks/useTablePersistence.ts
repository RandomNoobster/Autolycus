/**
 * useTablePersistence Hook
 *
 * This hook provides persistence for Mantine React Table UI preferences
 * using localStorage. It saves:
 * - Column visibility
 * - Column order
 * - Density setting
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  MRT_ColumnOrderState,
  MRT_DensityState,
  MRT_VisibilityState,
} from 'mantine-react-table';

interface TablePreferences {
  columnVisibility: MRT_VisibilityState;
  columnOrder: MRT_ColumnOrderState;
  density: MRT_DensityState;
}

/** App defaults for a table; used to merge with localStorage and for reset. */
export interface TablePersistenceDefaults {
  columnVisibility: MRT_VisibilityState;
  columnOrder: MRT_ColumnOrderState;
  density: MRT_DensityState;
}

interface UseTablePersistenceReturn {
  // Current state values
  columnVisibility: MRT_VisibilityState;
  columnOrder: MRT_ColumnOrderState;
  density: MRT_DensityState;

  // State setters (also persist to localStorage)
  setColumnVisibility: (
    updater:
      | MRT_VisibilityState
      | ((prev: MRT_VisibilityState) => MRT_VisibilityState)
  ) => void;
  setColumnOrder: (
    updater:
      | MRT_ColumnOrderState
      | ((prev: MRT_ColumnOrderState) => MRT_ColumnOrderState)
  ) => void;
  setDensity: (
    updater: MRT_DensityState | ((prev: MRT_DensityState) => MRT_DensityState)
  ) => void;

  // Reset to defaults
  resetPreferences: () => void;
}

const DEFAULT_PREFERENCES: TablePreferences = {
  columnVisibility: {},
  columnOrder: [],
  density: 'md',
};

function cloneDefaults(defaults: TablePersistenceDefaults): TablePreferences {
  return {
    columnVisibility: { ...defaults.columnVisibility },
    columnOrder: [...defaults.columnOrder],
    density: defaults.density,
  };
}

function mergeColumnOrder(
  defaultOrder: MRT_ColumnOrderState,
  storedOrder: unknown
): MRT_ColumnOrderState {
  if (!Array.isArray(storedOrder) || storedOrder.length === 0) {
    return [...defaultOrder];
  }
  const valid = new Set(defaultOrder);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const id of storedOrder) {
    if (typeof id !== 'string') continue;
    if (valid.has(id) && !seen.has(id)) {
      out.push(id);
      seen.add(id);
    }
  }
  for (const id of defaultOrder) {
    if (!seen.has(id)) {
      out.push(id);
      seen.add(id);
    }
  }
  return out;
}

function mergeWithDefaults(
  defaults: TablePersistenceDefaults,
  parsed: Partial<TablePreferences>
): TablePreferences {
  const storedVis = parsed.columnVisibility;
  return {
    columnVisibility: {
      ...defaults.columnVisibility,
      ...(storedVis && typeof storedVis === 'object' ? storedVis : {}),
    },
    columnOrder: mergeColumnOrder(
      defaults.columnOrder,
      parsed.columnOrder
    ),
    density:
      parsed.density !== undefined && parsed.density !== null
        ? parsed.density
        : defaults.density,
  };
}

/**
 * Load preferences from localStorage.
 */
function loadPreferences(
  key: string,
  defaults?: TablePersistenceDefaults
): TablePreferences {
  try {
    const stored = localStorage.getItem(key);
    if (stored) {
      const parsed = JSON.parse(stored) as Partial<TablePreferences>;
      if (defaults) {
        return mergeWithDefaults(defaults, parsed);
      }
      return {
        ...DEFAULT_PREFERENCES,
        ...parsed,
      };
    }
  } catch (error) {
    console.warn(`Failed to load table preferences for ${key}:`, error);
  }
  if (defaults) {
    return cloneDefaults(defaults);
  }
  return DEFAULT_PREFERENCES;
}

/**
 * Save preferences to localStorage.
 */
function savePreferences(key: string, preferences: TablePreferences): void {
  try {
    localStorage.setItem(key, JSON.stringify(preferences));
  } catch (error) {
    console.warn(`Failed to save table preferences for ${key}:`, error);
  }
}

/**
 * Hook for persisting table preferences.
 *
 * @param tableId - Unique identifier for the table (e.g., 'raids')
 * @param defaults - Optional app defaults; merged with stored prefs and used on reset
 * @returns State values and setters for table preferences
 */
export function useTablePersistence(
  tableId: string,
  defaults?: TablePersistenceDefaults
): UseTablePersistenceReturn {
  const storageKey = `autolycus-table-${tableId}`;
  const defaultsRef = useRef(defaults);
  defaultsRef.current = defaults;

  // Initialize state from localStorage
  const [preferences, setPreferences] = useState<TablePreferences>(() =>
    loadPreferences(storageKey, defaults)
  );

  // Save to localStorage whenever preferences change
  useEffect(() => {
    savePreferences(storageKey, preferences);
  }, [storageKey, preferences]);

  // Column visibility setter
  const setColumnVisibility = useCallback(
    (
      updater:
        | MRT_VisibilityState
        | ((prev: MRT_VisibilityState) => MRT_VisibilityState)
    ) => {
      setPreferences((prev) => ({
        ...prev,
        columnVisibility:
          typeof updater === 'function'
            ? updater(prev.columnVisibility)
            : updater,
      }));
    },
    []
  );

  // Column order setter
  const setColumnOrder = useCallback(
    (
      updater:
        | MRT_ColumnOrderState
        | ((prev: MRT_ColumnOrderState) => MRT_ColumnOrderState)
    ) => {
      setPreferences((prev) => ({
        ...prev,
        columnOrder:
          typeof updater === 'function' ? updater(prev.columnOrder) : updater,
      }));
    },
    []
  );

  // Density setter
  const setDensity = useCallback(
    (
      updater: MRT_DensityState | ((prev: MRT_DensityState) => MRT_DensityState)
    ) => {
      setPreferences((prev) => ({
        ...prev,
        density:
          typeof updater === 'function' ? updater(prev.density) : updater,
      }));
    },
    []
  );

  // Reset to defaults
  const resetPreferences = useCallback(() => {
    const d = defaultsRef.current;
    if (d) {
      setPreferences(cloneDefaults(d));
    } else {
      setPreferences(DEFAULT_PREFERENCES);
    }
    localStorage.removeItem(storageKey);
  }, [storageKey]);

  return {
    columnVisibility: preferences.columnVisibility,
    columnOrder: preferences.columnOrder,
    density: preferences.density,
    setColumnVisibility,
    setColumnOrder,
    setDensity,
    resetPreferences,
  };
}
