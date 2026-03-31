/**
 * Resolves Discord OAuth web session state for sidebar.
 */

import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { getDiscordSession } from '@/api/auth';

export type SidebarDiscordSession =
  | { status: 'loading' }
  | { status: 'guest' }
  | {
      status: 'signed_in';
      discordUserId: number;
      username?: string;
      displayName?: string;
      avatarUrl?: string;
      expiresAtSec: number;
    };

export function useSidebarDiscordSession(): SidebarDiscordSession {
  const location = useLocation();
  const [state, setState] = useState<SidebarDiscordSession>({ status: 'loading' });
  const hasResolvedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    async function refresh() {
      // Keep the previously resolved state during route changes.
      // This avoids sidebar skeleton flashes while still refreshing in background.
      if (!cancelled && !hasResolvedRef.current) {
        setState({ status: 'loading' });
      }
      try {
        const v = await getDiscordSession();
        if (cancelled) return;
        if (!v.authenticated || !v.discord_user_id) {
          setState({ status: 'guest' });
          hasResolvedRef.current = true;
          return;
        }
        const ts = typeof v.authenticated_at === 'number' ? v.authenticated_at : Math.floor(Date.now() / 1000);
        setState({
          status: 'signed_in',
          discordUserId: v.discord_user_id,
          username: typeof v.username === 'string' ? v.username : undefined,
          displayName: typeof v.global_name === 'string' ? v.global_name : undefined,
          avatarUrl:
            typeof v.avatar_url === 'string' && v.avatar_url
              ? v.avatar_url
              : typeof v.avatar === 'string' && v.avatar
              ? `https://cdn.discordapp.com/avatars/${v.discord_user_id}/${v.avatar}.png?size=128`
              : undefined,
          expiresAtSec: ts + 7 * 24 * 3600,
        });
        hasResolvedRef.current = true;
      } catch {
        if (!cancelled) {
          setState({ status: 'guest' });
          hasResolvedRef.current = true;
        }
      }
    }

    void refresh();
    return () => {
      cancelled = true;
    };
  }, [location.key]);

  return state;
}
