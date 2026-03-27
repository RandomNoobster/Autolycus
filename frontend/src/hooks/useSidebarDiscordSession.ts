/**
 * Resolves Discord-linked API session for sidebar (raid token in URL or localStorage).
 */

import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { verifyToken } from '@/api/auth';
import {
  ACCESS_TOKEN_MAX_AGE_SEC,
  AUTH_STORAGE_CHANGED_EVENT,
  readStoredAccessToken,
} from '@/lib/accessTokenStorage';

const STORAGE_KEY_PREFIX = 'autolycus-access-token-v1';

export type SidebarDiscordSession =
  | { status: 'loading' }
  | { status: 'guest' }
  | {
      status: 'signed_in';
      discordUserId: number;
      expiresAtSec: number;
    };

function parseDiscordUserId(payload: Record<string, unknown>): number | null {
  const raw = payload.user_id;
  if (typeof raw === 'number' && Number.isFinite(raw)) return raw;
  if (typeof raw === 'string' && /^\d+$/.test(raw)) return parseInt(raw, 10);
  return null;
}

export function useSidebarDiscordSession(): SidebarDiscordSession {
  const location = useLocation();
  const urlToken = useMemo(
    () => new URLSearchParams(location.search).get('token'),
    [location.search]
  );
  const [state, setState] = useState<SidebarDiscordSession>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;

    async function refresh() {
      const stored = readStoredAccessToken('raids');
      const token = urlToken || stored?.token;
      if (!token) {
        if (!cancelled) setState({ status: 'guest' });
        return;
      }
      if (!cancelled) setState({ status: 'loading' });
      try {
        const v = await verifyToken(token);
        if (cancelled) return;
        if (!v.valid || !v.payload) {
          setState({ status: 'guest' });
          return;
        }
        const userId = parseDiscordUserId(v.payload as Record<string, unknown>);
        if (userId === null) {
          setState({ status: 'guest' });
          return;
        }
        const ts =
          typeof v.payload.timestamp === 'number'
            ? v.payload.timestamp
            : Math.floor(Date.now() / 1000);
        setState({
          status: 'signed_in',
          discordUserId: userId,
          expiresAtSec: ts + ACCESS_TOKEN_MAX_AGE_SEC,
        });
      } catch {
        if (!cancelled) setState({ status: 'guest' });
      }
    }

    void refresh();

    const onAuthChanged = () => {
      void refresh();
    };

    const onStorage = (e: StorageEvent) => {
      if (e.key && e.key.startsWith(STORAGE_KEY_PREFIX)) {
        void refresh();
      }
    };

    window.addEventListener(AUTH_STORAGE_CHANGED_EVENT, onAuthChanged);
    window.addEventListener('storage', onStorage);
    return () => {
      cancelled = true;
      window.removeEventListener(AUTH_STORAGE_CHANGED_EVENT, onAuthChanged);
      window.removeEventListener('storage', onStorage);
    };
  }, [urlToken]);

  return state;
}
