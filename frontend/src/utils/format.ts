/**
 * Formatting Utilities
 *
 * Functions for formatting numbers, currency, and other display values.
 */

const METRIC_UNITS = [
  [1e12, 'T'],
  [1e9, 'B'],
  [1e6, 'M'],
  [1e3, 'k'],
] as const;

/**
 * Format a number with metric prefixes (k, M, B, T).
 *
 * @param value - The number to format
 * @param decimals - Number of decimal places (default: 1)
 * @returns Formatted string with metric prefix
 *
 * @example
 * formatMetric(1234) // "1.2k"
 * formatMetric(5000000) // "5.0M"
 * formatMetric(999999) // "1.0M"
 * formatMetric(523.78) // "523.8"
 */
export function formatMetric(value: number, decimals: number = 1): string {
  if (!Number.isFinite(value)) return '—';
  const abs = Math.abs(value);
  const sign = value < 0 ? '-' : '';

  for (let i = 0; i < METRIC_UNITS.length; i++) {
    const [size, suffix] = METRIC_UNITS[i];
    if (abs < size) continue;
    const scaled = (abs / size).toFixed(decimals);
    // 999 950 rounds to "1000.0k": show it in the next unit up instead.
    if (Number(scaled) >= 1000 && i > 0) {
      const [biggerSize, biggerSuffix] = METRIC_UNITS[i - 1];
      return `${sign}${(abs / biggerSize).toFixed(decimals)}${biggerSuffix}`;
    }
    return `${sign}${scaled}${suffix}`;
  }

  // Below 1000: round, without padding whole numbers ("523", "523.8").
  const rounded = Number(abs.toFixed(decimals));
  if (rounded === 0) return '0';
  if (rounded >= 1000) return `${sign}${(1).toFixed(decimals)}k`;
  return `${sign}${rounded}`;
}

/** Non-breaking space, so a number never wraps between its digit groups. */
const THOUSANDS_SEPARATOR = String.fromCharCode(0xa0);

/**
 * Format a number using spaces as thousands separators.
 *
 * @param value - Number to format
 * @param decimals - Fixed decimal places; when omitted, rounds to at most 2
 */
export function formatNumber(value: number, decimals?: number): string {
  if (!Number.isFinite(value)) return '—';
  const formatted =
    decimals !== undefined ? value.toFixed(decimals) : String(Math.round(value * 100) / 100);
  const [integerPart, decimalPart] = formatted.split('.');
  const grouped = integerPart.replace(/\B(?=(\d{3})+(?!\d))/g, THOUSANDS_SEPARATOR);
  return decimalPart ? `${grouped}.${decimalPart}` : grouped;
}

/**
 * Format a number as currency with optional metric prefix.
 *
 * @param value - The number to format
 * @param useMetric - Whether to use metric prefixes (default: true)
 * @returns Formatted currency string
 *
 * @example
 * formatCurrency(1234567) // "$1.2M"
 * formatCurrency(1234567, false) // "$1 234 567"
 */
export function formatCurrency(value: number, useMetric: boolean = true): string {
  if (useMetric) {
    return `$${formatMetric(value)}`;
  }
  const decimals = Number.isInteger(value) ? undefined : 2;
  return `$${formatNumber(value, decimals)}`;
}

/**
 * Format a percentage value.
 *
 * @param value - The percentage value (0-100)
 * @param decimals - Number of decimal places (default: 0)
 * @returns Formatted percentage string
 *
 * @example
 * formatPercentage(75.5) // "76%"
 * formatPercentage(75.5, 1) // "75.5%"
 */
export function formatPercentage(value: number, decimals: number = 0): string {
  return `${value.toFixed(decimals)}%`;
}

/**
 * Get color for a profit/loss value.
 *
 * @param value - The numeric value
 * @returns Mantine color string
 *
 * @example
 * getProfitColor(1000000) // "green"
 * getProfitColor(-500) // "red"
 */
export function getProfitColor(value: number): string {
  if (value > 500000) return 'green';
  if (value > 100000) return 'teal';
  if (value > 0) return 'blue';
  if (value < -100000) return 'red';
  if (value < 0) return 'orange';
  return 'gray';
}

/**
 * Format MMR (Military Minimum Requirement) string.
 *
 * @param barracks - Number of barracks
 * @param factories - Number of factories
 * @param hangars - Number of hangars/airbases
 * @param drydocks - Number of drydocks
 * @returns Formatted MMR string (e.g., "5/5/3/1")
 */
export function formatMMR(
  barracks: number,
  factories: number,
  hangars: number,
  drydocks: number
): string {
  return `${barracks}/${factories}/${hangars}/${drydocks}`;
}
