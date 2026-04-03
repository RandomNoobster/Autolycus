/**
 * Shared parsing for raids table column filters and RaidsPage sidebar sync.
 */

export const INACTIVE_PRESET_DAYS = ['3', '5', '7', '14', '30'] as const;

export const LOOT_PRESET_AMOUNTS = ['0', '5000000', '10000000', '20000000'] as const;

export type LootPresetAmount = (typeof LOOT_PRESET_AMOUNTS)[number];

/** Parse numeric values that might contain $, %, +, commas, and k/m/b suffix */
export function parseNumericValue(value: unknown): number {
  if (typeof value === 'number') return value;
  if (typeof value === 'string') {
    const s = value.trim().toLowerCase();
    const cleaned = s.replace(/[,$%+\s]/g, '');
    const match = cleaned.match(/^(-?\d*\.?\d+)([kmb])?$/i);
    if (match) {
      const base = parseFloat(match[1]);
      const suf = (match[2] || '').toLowerCase();
      const mult = suf === 'k' ? 1e3 : suf === 'm' ? 1e6 : suf === 'b' ? 1e9 : 1;
      const num = base * mult;
      return Number.isNaN(num) ? 0 : num;
    }
    const parsed = parseFloat(cleaned.replace(/[^0-9.-]/g, ''));
    return Number.isNaN(parsed) ? 0 : parsed;
  }
  return 0;
}

export function positionsArrayKey(arr: string[]): string {
  return JSON.stringify([...arr].map((s) => String(s).trim()).filter(Boolean).sort());
}

export function setsEqualSorted(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const sa = [...a].sort();
  const sb = [...b].sort();
  return sa.every((v, i) => v === sb[i]);
}

const APPS_OR_NONE_SET = ['APPLICANT', 'NOALLIANCE'];
const NO_ALLIANCE_SET = ['NOALLIANCE'];

export function classifyAlliancePositionFilter(value: unknown): {
  scopeMode: 'preset' | 'custom';
  scopePreset: 'all' | 'apps_or_none' | 'no_alliance';
  scopeCustomPositions: string[];
} {
  const raw = Array.isArray(value)
    ? value.map((v) => String(v).trim()).filter(Boolean)
    : value == null || value === ''
      ? []
      : [String(value).trim()].filter(Boolean);
  if (raw.length === 0) {
    return { scopeMode: 'preset', scopePreset: 'all', scopeCustomPositions: [] };
  }
  if (setsEqualSorted(raw, APPS_OR_NONE_SET)) {
    return { scopeMode: 'preset', scopePreset: 'apps_or_none', scopeCustomPositions: [] };
  }
  if (setsEqualSorted(raw, NO_ALLIANCE_SET)) {
    return { scopeMode: 'preset', scopePreset: 'no_alliance', scopeCustomPositions: [] };
  }
  return { scopeMode: 'custom', scopePreset: 'all', scopeCustomPositions: [...raw].sort() };
}

export function classifyInactiveColumnValue(value: unknown): {
  inactiveMode: 'none' | 'preset' | 'custom';
  inactivePreset: string;
  inactiveCustom: string;
} {
  if (value === undefined || value === null || value === '') {
    return { inactiveMode: 'none', inactivePreset: '3', inactiveCustom: '' };
  }
  const str = String(value).trim();
  if (!str) {
    return { inactiveMode: 'none', inactivePreset: '3', inactiveCustom: '' };
  }
  const num = parseNumericValue(str);
  if (num <= 0) {
    return { inactiveMode: 'none', inactivePreset: '3', inactiveCustom: '' };
  }
  for (const p of INACTIVE_PRESET_DAYS) {
    if (num === Number(p)) {
      return { inactiveMode: 'preset', inactivePreset: p, inactiveCustom: '' };
    }
  }
  return { inactiveMode: 'custom', inactivePreset: '3', inactiveCustom: str };
}

/** True when the user typed a k/m/b scale suffix (so we keep their string for table + sidebar sync). */
function lootInputUsesScaleSuffix(str: string): boolean {
  const s = str.trim().toLowerCase().replace(/[,$%+\s]/g, '');
  const match = s.match(/^(-?\d*\.?\d+)([kmb])?$/i);
  return Boolean(match?.[2]);
}

export function classifyLootColumnValue(value: unknown): {
  lootMode: 'none' | 'preset' | 'custom';
  lootPreset: string;
  lootCustom: string;
} {
  if (value === undefined || value === null || value === '') {
    return { lootMode: 'none', lootPreset: '0', lootCustom: '' };
  }
  const str = String(value).trim();
  if (!str) {
    return { lootMode: 'none', lootPreset: '0', lootCustom: '' };
  }
  const num = parseNumericValue(str);
  const keepRawForSync = lootInputUsesScaleSuffix(str);

  // Only map to dollar presets when the value wasn't entered with k/m/b shorthand.
  // Otherwise "10m" would collapse to preset 10000000 and the table would show the long form.
  if (!keepRawForSync) {
    for (const p of LOOT_PRESET_AMOUNTS) {
      if (p === '0') continue;
      if (Math.abs(num - Number(p)) < 1) {
        return { lootMode: 'preset', lootPreset: p, lootCustom: '' };
      }
    }
  }
  if (num <= 0) {
    return { lootMode: 'none', lootPreset: '0', lootCustom: '' };
  }
  return { lootMode: 'custom', lootPreset: '0', lootCustom: str };
}

export function normalizeDefSlotsFilterValue(value: unknown): string {
  if (value === undefined || value === null || value === '') return '';
  const n = parseNumericValue(value);
  if (!Number.isFinite(n)) return '';
  const clamped = Math.min(Math.max(Math.round(n), 0), 3);
  return String(clamped);
}

export function defSlotsFilterCompareKey(value: unknown): string {
  const s = normalizeDefSlotsFilterValue(value);
  return s === '' ? '' : s;
}
