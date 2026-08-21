import { createSearchParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useCallback } from 'react';

const NUKE_TARGETS_PATH = '/nuke-targets';

function isNukeTargetsPathname(): boolean {
  if (typeof window === 'undefined') return false;
  const p = window.location.pathname.replace(/\/$/, '') || '/';
  return p === NUKE_TARGETS_PATH;
}

export function useNukeTargetsSearchParams() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const setNukeTargetsSearchParams = useCallback(
    (
      nextInit:
        | URLSearchParams
        | Record<string, string | string[]>
        | ((prev: URLSearchParams) => URLSearchParams),
      navigateOpts?: { replace?: boolean }
    ) => {
      if (!isNukeTargetsPathname()) return;

      const prev = new URLSearchParams(window.location.search);
      const next = createSearchParams(
        typeof nextInit === 'function' ? nextInit(prev) : nextInit
      );
      const qs = next.toString();
      navigate(
        { pathname: NUKE_TARGETS_PATH, search: qs ? `?${qs}` : '' },
        { replace: navigateOpts?.replace ?? false }
      );
    },
    [navigate]
  );

  return [searchParams, setNukeTargetsSearchParams] as const;
}
