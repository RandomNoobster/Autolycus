/**
 * Builds in-app navigation URLs so query strings match what each route reads.
 * Raid Targets uses many deep-link params; other pages ignore most of them.
 */

export function internalNavPath(pathname: string, search: string): string {
  const sp = new URLSearchParams(search);

  if (pathname === '/raids') {
    sp.delete('token');
    sp.delete('code');
    sp.delete('auto');
    sp.delete('redirect');
    const q = sp.toString();
    return `/raids${q ? `?${q}` : ''}`;
  }

  if (pathname === '/nuke-targets') {
    sp.delete('token');
    sp.delete('code');
    sp.delete('auto');
    sp.delete('redirect');
    const q = sp.toString();
    return `/nuke-targets${q ? `?${q}` : ''}`;
  }

  sp.delete('token');
  sp.delete('code');
  sp.delete('auto');
  sp.delete('redirect');

  if (pathname === '/') {
    return '/';
  }

  if (pathname === '/builds') {
    const next = new URLSearchParams();
    const nation =
      sp.get('nationId') ||
      sp.get('nation_id') ||
      sp.get('attackerNationId');
    if (nation) {
      next.set('nationId', nation);
    }
    const q = next.toString();
    return `/builds${q ? `?${q}` : ''}`;
  }

  if (pathname === '/damage') {
    const next = new URLSearchParams();
    const n1 = sp.get('nation1');
    const n2 = sp.get('nation2');
    if (n1) {
      next.set('nation1', n1);
    }
    if (n2) {
      next.set('nation2', n2);
    }
    const q = next.toString();
    return `/damage${q ? `?${q}` : ''}`;
  }

  return pathname;
}
