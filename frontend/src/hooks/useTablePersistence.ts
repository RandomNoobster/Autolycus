/**
 * useTablePersistence Hook
 *
 * This hook provides persistence for Mantine React Table UI preferences
 * using localStorage. It saves:
 * - Column visibility
 * - Column order
 * - Density setting
 */

import { useCallback, useEffect, useState } from 'react';
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

/**
 * Load preferences from localStorage.
 */
function loadPreferences(key: string): TablePreferences {
  try {
    const stored = localStorage.getItem(key);
    if (stored) {
      const parsed = JSON.parse(stored);
      return {
        ...DEFAULT_PREFERENCES,
        ...parsed,
      };
    }
  } catch (error) {
    console.warn(`Failed to load table preferences for ${key}:`, error);
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
 * @param tableId - Unique identifier for the table (e.g., 'raids-table')
 * @returns State values and setters for table preferences
 */
export function useTablePersistence(tableId: string): UseTablePersistenceReturn {
  const storageKey = `autolycus-table-${tableId}`;

  // Initialize state from localStorage
  const [preferences, setPreferences] = useState<TablePreferences>(() =>
    loadPreferences(storageKey)
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
    setPreferences(DEFAULT_PREFERENCES);
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
