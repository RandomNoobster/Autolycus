import { usePageSearchParams } from './usePageSearchParams';

/** Query-string state for Nuke Targets; see usePageSearchParams. */
export function useNukeTargetsSearchParams() {
  return usePageSearchParams('/nuke-targets');
}
