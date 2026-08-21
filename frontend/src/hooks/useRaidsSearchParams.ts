/**
 * Raids URL updates must not use setSearchParams's relative `navigate("?…")` after the user
 * has left /raids: useSearchParams captures a stale pathname, so a late effect can "snap" the
 * app back to /raids. This hook commits with an explicit pathname and bails out if we're
 * no longer on Raid Targets.
 */

import { useCallback } from 'react';
import { createSearchParams, useNavigate, useSearchParams } from 'react-router-dom';

const RAIDS_PATH = '/raids';

function isRaidsPathname(): boolean {
  if (typeof window === 'undefined') return false;
  const p = window.location.pathname.replace(/\/$/, '') || '/';
  return p === RAIDS_PATH;
}

export function useRaidsSearchParams() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const setRaidsSearchParams = useCallback(
    (
      nextInit:
        | URLSearchParams
        | Record<string, string | string[]>
        | ((prev: URLSearchParams) => URLSearchParams),
      navigateOpts?: { replace?: boolean }
    ) => {
      if (!isRaidsPathname()) return;

      const prev = new URLSearchParams(window.location.search);
      const next = createSearchParams(
        typeof nextInit === 'function' ? nextInit(prev) : nextInit
      );
      const qs = next.toString();
      navigate(
        { pathname: RAIDS_PATH, search: qs ? `?${qs}` : '' },
        { replace: navigateOpts?.replace ?? false }
      );
    },
    [navigate]
  );

  return [searchParams, setRaidsSearchParams] as const;
}
