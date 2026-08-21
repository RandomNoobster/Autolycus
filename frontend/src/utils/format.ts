/**
 * Formatting Utilities
 *
 * Functions for formatting numbers, currency, and other display values.
 */

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
 * formatMetric(3200000000) // "3.2B"
 */
export function formatMetric(value: number, decimals: number = 1): string {
  if (value === 0) return '0';
  
  const abs = Math.abs(value);
  const sign = value < 0 ? '-' : '';
  
  if (abs >= 1e12) {
    return `${sign}${(abs / 1e12).toFixed(decimals)}T`;
  }
  if (abs >= 1e9) {
    return `${sign}${(abs / 1e9).toFixed(decimals)}B`;
  }
  if (abs >= 1e6) {
    return `${sign}${(abs / 1e6).toFixed(decimals)}M`;
  }
  if (abs >= 1e3) {
    return `${sign}${(abs / 1e3).toFixed(decimals)}k`;
  }
  
  return value.toString();
}

/**
 * Format a number using spaces as thousands separators.
 *
 * @param value - Number to format
 * @param decimals - Optional fixed decimal precision
 */
export function formatNumber(value: number, decimals?: number): string {
  const formatted = decimals !== undefined ? value.toFixed(decimals) : `${value}`;
  const [integerPart, decimalPart] = formatted.split('.');
  const useComma = decimals !== undefined || !Number.isInteger(value);
  const delimiter = useComma ? ',' : ' ';
  const grouped = integerPart.replace(/\B(?=(\d{3})+(?!\d))/g, delimiter);
  return decimalPart && decimalPart.length > 0 ? `${grouped}.${decimalPart}` : grouped;
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
 * formatCurrency(1234567, false) // "$1,234,567"
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
