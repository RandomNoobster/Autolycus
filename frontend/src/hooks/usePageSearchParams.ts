/**
 * Query-string updates for one page.
 *
 * A late effect must not use setSearchParams's relative `navigate("?…")` after the user has left
 * the page: useSearchParams captures a stale pathname, so the app would "snap" back. This commits
 * with an explicit pathname, does nothing once the user is on another page, and skips writes that
 * change nothing (each navigate re-renders the whole app with a new location key).
 */

import { useCallback } from 'react';
import { createSearchParams, useNavigate, useSearchParams } from 'react-router-dom';

type SearchParamsInit =
  | URLSearchParams
  | Record<string, string | string[]>
  | ((prev: URLSearchParams) => URLSearchParams);

function isOnPath(path: string): boolean {
  if (typeof window === 'undefined') return false;
  // React Router matches routes case-insensitively and ignores a trailing slash.
  const current = window.location.pathname.replace(/\/+$/, '').toLowerCase() || '/';
  return current === path.toLowerCase();
}

export function usePageSearchParams(path: string) {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const setPageSearchParams = useCallback(
    (nextInit: SearchParamsInit, navigateOpts?: { replace?: boolean }) => {
      if (!isOnPath(path)) return;

      const prev = new URLSearchParams(window.location.search);
      const qs = createSearchParams(
        typeof nextInit === 'function' ? nextInit(prev) : nextInit
      ).toString();
      if (qs === prev.toString()) return;
      navigate(
        { pathname: window.location.pathname, search: qs ? `?${qs}` : '' },
        { replace: navigateOpts?.replace ?? false }
      );
    },
    [navigate, path]
  );

  return [searchParams, setPageSearchParams] as const;
}
