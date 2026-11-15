import { usePageSearchParams } from './usePageSearchParams';

/** Query-string state for Raid Targets; see usePageSearchParams. */
export function useRaidsSearchParams() {
  return usePageSearchParams('/raids');
}
