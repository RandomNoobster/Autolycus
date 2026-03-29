/**
 * Builds in-app navigation URLs so query strings match what each route reads.
 * Raid Targets uses many deep-link params; other pages ignore most of them.
 */

import { readStoredAccessToken } from '@/lib/accessTokenStorage';

export function internalNavPath(pathname: string, search: string): string {
  const sp = new URLSearchParams(search);

  if (pathname === '/raids') {
    const hasToken =
      sp.has('token') || readStoredAccessToken('raids') !== null;
    if (hasToken) {
      return `/raids${search}`;
    }
    return `/token-request?type=raids&redirect=/raids&auto=true`;
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
