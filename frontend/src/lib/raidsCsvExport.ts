import type { Column } from '@tanstack/react-table';
import type { MRT_TableInstance } from 'mantine-react-table';

import type { RaidTarget } from '@/types';

/** RFC 4180-style escaping; quotes fields that need it (commas, quotes, newlines, leading formula chars). */
export function escapeCsvCell(value: unknown): string {
  if (value === null || value === undefined) return '';
  const s = String(value);
  if (s === '') return '';
  if (/[",\r\n]/.test(s) || /^[=+\-@]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

function exportValueForColumn(column: Column<RaidTarget, unknown>, target: RaidTarget): unknown {
  const id = column.id;
  if (id === 'reminder') return target.hasReminderActive;
  if (id === 'alliancePosition') {
    return target.alliancePosition === 'NOALLIANCE' ? 'None' : target.alliancePosition;
  }
  if (id === 'updatedAt') {
    const ts = target.updatedAt;
    if (ts == null) return '';
    const n = Number(ts);
    if (!Number.isFinite(n) || n <= 0) return '';
    return new Date(n * 1000).toISOString();
  }
  const key = id as keyof RaidTarget;
  if (key in target) return target[key];
  return '';
}

function headerLabel(column: Column<RaidTarget, unknown>): string {
  const h = column.columnDef.header;
  if (typeof h === 'string' && h.length > 0) return h;
  return column.id;
}

/** All rows after filters, search, and sort; not limited to the current page. */
export function buildRaidsCsv(table: MRT_TableInstance<RaidTarget>): string {
  const rows = table.getPrePaginationRowModel().rows;
  const visibleCols = table.getVisibleLeafColumns();
  const headerRow = visibleCols.map((c) => escapeCsvCell(headerLabel(c))).join(',');
  const dataRows = rows.map((row) =>
    visibleCols.map((col) => escapeCsvCell(exportValueForColumn(col, row.original))).join(','),
  );
  return [headerRow, ...dataRows].join('\r\n');
}

export function downloadCsv(filename: string, csvText: string): void {
  const blob = new Blob([`\uFEFF${csvText}`], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function raidsCsvFilename(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `raids-${y}-${m}-${day}.csv`;
}
