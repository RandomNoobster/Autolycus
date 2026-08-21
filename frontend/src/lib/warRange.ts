/**
 * PnW offensive war range helpers.
 * Exact range is 0.75×–2.5× score; query bounds bias inward so we hide
 * edge nations rather than showing ones that fail declare.
 */

export function warRangeQueryBounds(score: number): { minScore: number; maxScore: number } {
  return {
    minScore: Math.max(15, Math.ceil(score * 0.75)),
    maxScore: Math.floor(score * 2.5),
  };
}
