/**
 * PnW offensive war range helpers.
 * Exact range is 0.75×–2.5× score; query bounds bias inward so we hide
 * edge nations rather than showing ones that fail declare.
 */

/** Lowest score the raid list asks for (the API clamps to the same floor). */
export const MIN_QUERY_SCORE = 15;

export function warRangeQueryBounds(score: number): { minScore: number; maxScore: number } {
  return {
    minScore: Math.max(MIN_QUERY_SCORE, Math.ceil(score * 0.75)),
    maxScore: Math.floor(score * 2.5),
  };
}
