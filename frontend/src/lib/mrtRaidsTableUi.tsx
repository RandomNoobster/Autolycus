/**
 * Shared Mantine React Table UI pieces aligned with the raids table styling.
 */

import { useEffect, useRef, useState } from 'react';
import { Box, NumberInput, TextInput, Tooltip } from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { parseNumericValue } from '@/lib/raidFilterParsing';

export const MRT_RAIDS_BODY_CELL_PAD = {
  paddingTop: 2,
  paddingBottom: 2,
  paddingLeft: 6,
  paddingRight: 6,
} as const;

export const wrappedHeader = (text: string) => (
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

export function headerWithTooltip(text: string, description: string) {
  return (
    <Tooltip label={description} multiline maw={280} withinPortal>
      {wrappedHeader(text)}
    </Tooltip>
  );
}

export function columnFilterString(value: unknown): string {
  if (value === undefined || value === null || value === '') return '';
  return String(value);
}

function numberInputValueFromFilterString(s: string): string | number {
  if (s === '') return '';
  const n = Number(s);
  return Number.isFinite(n) ? n : s;
}

type FilterableRow = { getValue: (id: string) => unknown };

export const minOnlyFilter = (row: FilterableRow, id: string, filterValue: unknown) => {
  if (filterValue === undefined || filterValue === null || filterValue === '') return true;
  return parseNumericValue(row.getValue(id)) >= parseNumericValue(filterValue);
};

export const maxOnlyFilter = (row: FilterableRow, id: string, filterValue: unknown) => {
  if (filterValue === undefined || filterValue === null || filterValue === '') return true;
  return parseNumericValue(row.getValue(id)) <= parseNumericValue(filterValue);
};

type FilterColumn = { getFilterValue: () => unknown; setFilterValue: (v: unknown) => void };

/**
 * Local text that follows the column filter and writes back after a pause. It writes only
 * values the user typed: echoing the column's own value back (on mount, or after the sidebar
 * changed it) would rerun every filter and save the page state for nothing.
 */
function useDebouncedColumnFilter<T>(
  column: FilterColumn,
  toLocal: (filter: string) => T,
  toFilter: (local: T) => string,
  wait: number
) {
  const colStr = columnFilterString(column.getFilterValue());
  const [local, setLocal] = useState<T>(() => toLocal(colStr));
  const [debounced] = useDebouncedValue(local, wait);
  const lastEmittedRef = useRef(colStr);

  useEffect(() => {
    const next = toFilter(debounced);
    if (next === lastEmittedRef.current) return;
    lastEmittedRef.current = next;
    // undefined removes the filter instead of keeping an empty one that runs on every row.
    column.setFilterValue(next === '' ? undefined : next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  // Sidebar / URL sync updates column state without remounting this cell: keep the input in sync.
  useEffect(() => {
    if (colStr !== lastEmittedRef.current) {
      lastEmittedRef.current = colStr;
      setLocal(toLocal(colStr));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [colStr]);

  return [local, setLocal] as const;
}

const asText = (s: string) => s;
const numberToFilter = (v: string | number) =>
  v === '' || v === undefined || v === null ? '' : String(v);

/** Debounced text filter for min/max columns (accepts 10k, 2m, $5,000 …). */
export function DebouncedTextFilterInput({
  column,
  placeholder,
}: {
  column: FilterColumn;
  placeholder: string;
}) {
  const [raw, setRaw] = useDebouncedColumnFilter(column, asText, asText, 500);
  return (
    <TextInput
      placeholder={placeholder}
      value={raw}
      onChange={(e) => setRaw(e.currentTarget.value)}
      size="xs"
    />
  );
}

export function NumericMinOnlyFilterInput({
  column,
  max,
}: {
  column: FilterColumn;
  max?: number;
}) {
  const [localValue, setLocalValue] = useDebouncedColumnFilter(
    column,
    numberInputValueFromFilterString,
    numberToFilter,
    400
  );
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
}
