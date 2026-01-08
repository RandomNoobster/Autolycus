/**
 * useUrlParams Hook
 *
 * This hook provides bidirectional synchronization between URL query parameters
 * and React state. It's designed to work with Mantine React Table's state
 * for filtering, sorting, and pagination.
 *
 * Features:
 * - Extracts URL params on mount (for deep linking from Discord)
 * - Updates URL when table state changes
 * - Preserves the authentication token separately
 */

import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { MRT_ColumnFiltersState, MRT_SortingState } from 'mantine-react-table';

interface UseUrlParamsReturn {
  // The authentication token from URL
  token: string | null;

  // Initial column filters parsed from URL (for deep linking)
  initialColumnFilters: MRT_ColumnFiltersState;

  // Initial sorting parsed from URL
  initialSorting: MRT_SortingState;

  // Update URL when filters change
  setColumnFilters: (filters: MRT_ColumnFiltersState) => void;

  // Update URL when sorting changes
  setSorting: (sorting: MRT_SortingState) => void;

  // Get a specific query param value
  getParam: (key: string) => string | null;

  // Get all non-reserved params (for custom filters)
  getCustomParams: () => Record<string, string>;
}

// Reserved parameter names that shouldn't be treated as column filters
const RESERVED_PARAMS = ['token', 'sort', 'sortDir'];

/**
 * Parse column filters from URL search params.
 * Each query param (except reserved ones) becomes a column filter.
 *
 * Example: ?alliance=Eclipse&minCities=5 becomes:
 * [{ id: 'alliance', value: 'Eclipse' }, { id: 'minCities', value: '5' }]
 */
function parseFiltersFromUrl(
  searchParams: URLSearchParams
): MRT_ColumnFiltersState {
  const filters: MRT_ColumnFiltersState = [];

  searchParams.forEach((value, key) => {
    if (!RESERVED_PARAMS.includes(key) && value) {
      filters.push({ id: key, value });
    }
  });

  return filters;
}

/**
 * Parse sorting from URL search params.
 *
 * Example: ?sort=netIncome&sortDir=desc becomes:
 * [{ id: 'netIncome', desc: true }]
 */
function parseSortingFromUrl(searchParams: URLSearchParams): MRT_SortingState {
  const sortColumn = searchParams.get('sort');
  const sortDir = searchParams.get('sortDir');

  if (sortColumn) {
    return [{ id: sortColumn, desc: sortDir === 'desc' }];
  }

  return [];
}

/**
 * Serialize filters to URL params.
 */
function filtersToUrlParams(
  filters: MRT_ColumnFiltersState
): Record<string, string> {
  const params: Record<string, string> = {};

  filters.forEach((filter) => {
    if (filter.value !== undefined && filter.value !== null && filter.value !== '') {
      params[filter.id] = String(filter.value);
    }
  });

  return params;
}

/**
 * Serialize sorting to URL params.
 */
function sortingToUrlParams(
  sorting: MRT_SortingState
): Record<string, string> {
  if (sorting.length > 0) {
    return {
      sort: sorting[0].id,
      sortDir: sorting[0].desc ? 'desc' : 'asc',
    };
  }
  return {};
}

export function useUrlParams(): UseUrlParamsReturn {
  const [searchParams, setSearchParams] = useSearchParams();

  // Extract token - always preserve this
  const token = useMemo(() => searchParams.get('token'), [searchParams]);

  // Parse initial state from URL (memoized to prevent re-parsing)
  const initialColumnFilters = useMemo(
    () => parseFiltersFromUrl(searchParams),
    // Only compute on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const initialSorting = useMemo(
    () => parseSortingFromUrl(searchParams),
    // Only compute on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  // Update URL when column filters change
  const setColumnFilters = useCallback(
    (filters: MRT_ColumnFiltersState) => {
      setSearchParams((prev) => {
        const newParams = new URLSearchParams();

        // Always preserve token
        const existingToken = prev.get('token');
        if (existingToken) {
          newParams.set('token', existingToken);
        }

        // Preserve sorting
        const sort = prev.get('sort');
        const sortDir = prev.get('sortDir');
        if (sort) {
          newParams.set('sort', sort);
          if (sortDir) {
            newParams.set('sortDir', sortDir);
          }
        }

        // Add filter params
        const filterParams = filtersToUrlParams(filters);
        Object.entries(filterParams).forEach(([key, value]) => {
          newParams.set(key, value);
        });

        return newParams;
      }, { replace: true });
    },
    [setSearchParams]
  );

  // Update URL when sorting changes
  const setSorting = useCallback(
    (sorting: MRT_SortingState) => {
      setSearchParams((prev) => {
        const newParams = new URLSearchParams(prev);

        // Remove old sorting params
        newParams.delete('sort');
        newParams.delete('sortDir');

        // Add new sorting params
        const sortParams = sortingToUrlParams(sorting);
        Object.entries(sortParams).forEach(([key, value]) => {
          newParams.set(key, value);
        });

        return newParams;
      }, { replace: true });
    },
    [setSearchParams]
  );

  // Get a specific param
  const getParam = useCallback(
    (key: string) => searchParams.get(key),
    [searchParams]
  );

  // Get all non-reserved params
  const getCustomParams = useCallback(() => {
    const params: Record<string, string> = {};
    searchParams.forEach((value, key) => {
      if (!RESERVED_PARAMS.includes(key)) {
        params[key] = value;
      }
    });
    return params;
  }, [searchParams]);

  return {
    token,
    initialColumnFilters,
    initialSorting,
    setColumnFilters,
    setSorting,
    getParam,
    getCustomParams,
  };
}
