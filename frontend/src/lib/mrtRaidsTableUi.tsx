/**
 * Shared Mantine React Table UI pieces aligned with the raids table styling.
 */

import { useEffect, useRef, useState } from 'react';
import { Box, NumberInput, Tooltip } from '@mantine/core';
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

export const minOnlyFilter = (
  row: { getValue: (id: string) => unknown },
  id: string,
  filterValue: unknown
) => {
  if (filterValue === undefined || filterValue === null || filterValue === '') return true;
  return parseNumericValue(row.getValue(id)) >= parseNumericValue(filterValue);
};

export function NumericMinOnlyFilterInput({
  column,
  max,
}: {
  column: { getFilterValue: () => unknown; setFilterValue: (v: unknown) => void };
  max?: number;
}) {
  const colStr = columnFilterString(column.getFilterValue());
  const [localValue, setLocalValue] = useState<string | number>(() =>
    numberInputValueFromFilterString(colStr)
  );
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
}
