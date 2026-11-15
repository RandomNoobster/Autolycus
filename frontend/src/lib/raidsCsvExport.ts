import type { Column } from '@tanstack/react-table';
import type { MRT_TableInstance } from 'mantine-react-table';

import type { RaidTarget } from '@/types';

/** Spreadsheets run a cell starting with one of these as a formula, quoted or not. */
const FORMULA_START = /^[=+\-@\t\r]/;

/**
 * RFC 4180 escaping (quotes fields with commas, quotes or newlines). Text that a spreadsheet
 * would run as a formula (a player named "=HYPERLINK(…)") gets a leading apostrophe;
 * numbers, negative ones included, are left as numbers.
 */
export function escapeCsvCell(value: unknown): string {
  if (value === null || value === undefined) return '';
  let s = String(value);
  if (s === '') return '';
  if (typeof value === 'string' && FORMULA_START.test(s)) {
    s = `'${s}`;
  }
  if (/[",\r\n]/.test(s) || FORMULA_START.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

export interface RaidsCsvOptions {
  /** Current reminder state (the table may know about changes newer than its data). */
  hasReminder?: (target: RaidTarget) => boolean;
}

function exportValueForColumn(
  column: Column<RaidTarget, unknown>,
  target: RaidTarget,
  options: RaidsCsvOptions
): unknown {
  const id = column.id;
  if (id === 'reminder') return options.hasReminder ? options.hasReminder(target) : target.hasReminderActive;
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
export function buildRaidsCsv(table: MRT_TableInstance<RaidTarget>, options: RaidsCsvOptions = {}): string {
  const rows = table.getPrePaginationRowModel().rows;
  // MRT's own display columns (e.g. the 'mrt-row-spacer' that column resizing adds) hold no data.
  const visibleCols = table.getVisibleLeafColumns().filter((c) => !c.id.startsWith('mrt-'));
  const headerRow = visibleCols.map((c) => escapeCsvCell(headerLabel(c))).join(',');
  const dataRows = rows.map((row) =>
    visibleCols.map((col) => escapeCsvCell(exportValueForColumn(col, row.original, options))).join(','),
  );
  return [headerRow, ...dataRows].join('\r\n');
}

export function downloadCsv(filename: string, csvText: string): void {
  // A byte-order mark so Excel reads the file as UTF-8.
  const blob = new Blob([String.fromCharCode(0xfeff), csvText], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Revoking in the same tick can cancel the download in WebKit; give it time to start.
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export function raidsCsvFilename(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `raids-${y}-${m}-${day}.csv`;
}
