/**
 * Discord OAuth web session state, shared by the sidebar and pages through the query cache.
 */

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';

import { getDiscordSession, type DiscordSessionResponse } from '@/api/auth';
import { isTransientApiError } from '@/api/errors';

export const DISCORD_SESSION_QUERY_KEY = ['auth', 'session'] as const;

const DISCORD_SESSION_HINT_KEY = 'autolycus.discord_session_hint';

/**
 * Last resolved Discord session role for instant UI (e.g. home reminders promo)
 * while /api/auth/me is still in flight. Not security-sensitive.
 */
export function readDiscordSessionHint(): 'guest' | 'signed_in' | null {
  try {
    const v = sessionStorage.getItem(DISCORD_SESSION_HINT_KEY);
    if (v === 'guest' || v === 'signed_in') return v;
  } catch {
    /* private mode */
  }
  return null;
}

function persistDiscordSessionHint(value: 'guest' | 'signed_in') {
  try {
    sessionStorage.setItem(DISCORD_SESSION_HINT_KEY, value);
  } catch {
    /* private mode */
  }
}

export type SidebarDiscordSession =
  | { status: 'loading' }
  | { status: 'guest' }
  | {
      status: 'signed_in';
      username?: string;
      displayName?: string;
      avatarUrl?: string;
    };

function toSidebarSession(v: DiscordSessionResponse): SidebarDiscordSession {
  if (!v.authenticated) return { status: 'guest' };
  return {
    status: 'signed_in',
    username: typeof v.username === 'string' ? v.username : undefined,
    displayName: typeof v.global_name === 'string' ? v.global_name : undefined,
    // The API always sends avatar_url for a signed-in session (custom or default avatar).
    avatarUrl: typeof v.avatar_url === 'string' && v.avatar_url ? v.avatar_url : undefined,
  };
}

export function useSidebarDiscordSession(): SidebarDiscordSession {
  const { data, isError } = useQuery({
    queryKey: DISCORD_SESSION_QUERY_KEY,
    queryFn: getDiscordSession,
    select: toSidebarSession,
    staleTime: 5 * 60_000,
    // Picks up a logout or expiry from another tab when the user comes back.
    refetchOnWindowFocus: true,
    retry: (failureCount, error) => failureCount < 2 && isTransientApiError(error),
  });

  const resolvedStatus = data?.status;
  useEffect(() => {
    if (resolvedStatus === 'guest' || resolvedStatus === 'signed_in') {
      persistDiscordSessionHint(resolvedStatus);
    }
  }, [resolvedStatus]);

  // A failed background refresh keeps the last answer. /api/auth/me only fails when the
  // API can't be reached, so with no answer at all the sign-in button is still the right UI.
  if (data) return data;
  return isError ? { status: 'guest' } : { status: 'loading' };
}
