/**
 * Builds in-app navigation URLs so query strings match what each route reads.
 * Raid Targets and Nuke Targets keep their deep-link params; other pages keep only theirs.
 */

/** Params from old bot links and the OAuth round trip; no page reads them. */
const TRANSIENT_PARAMS = ['token', 'code', 'auto', 'redirect'];

function withSearch(pathname: string, params: URLSearchParams): string {
  const q = params.toString();
  return `${pathname}${q ? `?${q}` : ''}`;
}

export function internalNavPath(pathname: string, search: string): string {
  const sp = new URLSearchParams(search);
  TRANSIENT_PARAMS.forEach((key) => sp.delete(key));

  if (pathname === '/raids' || pathname === '/nuke-targets') {
    return withSearch(pathname, sp);
  }

  if (pathname === '/builds') {
    const next = new URLSearchParams();
    const nation = sp.get('nationId') || sp.get('nation_id') || sp.get('attackerNationId');
    if (nation) next.set('nationId', nation);
    return withSearch(pathname, next);
  }

  if (pathname === '/damage') {
    const next = new URLSearchParams();
    const n1 = sp.get('nation1');
    const n2 = sp.get('nation2');
    if (n1) next.set('nation1', n1);
    if (n2) next.set('nation2', n2);
    return withSearch(pathname, next);
  }

  return pathname;
}
