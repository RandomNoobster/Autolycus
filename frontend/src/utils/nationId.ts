/**
 * Nation ID parsing shared by every nation input.
 */

/**
 * A nation id from user input, or null when the input names no nation.
 *
 * Accepts plain digits, a Politics & War nation link (`/nation/id=123`,
 * `/nation/war/declare/id=123`, `?nation_id=123`) and the app's own search labels,
 * which end in "(ID 123)". Other links (alliances, cities) and names that merely
 * contain digits are rejected, so they can fall through to a name search.
 */
export function parseNationId(input: string): string | null {
  const trimmed = input.trim();
  if (/^\d+$/.test(trimmed)) return trimmed;
  const label = trimmed.match(/\(ID (\d+)\)$/i);
  if (label) return label[1];
  const link = trimmed.match(/(?:nation\/(?:war\/declare\/)?id=|nation_id=)(\d+)/i);
  return link ? link[1] : null;
}
