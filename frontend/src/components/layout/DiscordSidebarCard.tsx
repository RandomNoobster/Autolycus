/**
 * Discord session summary for the app sidebar (login button, or name and logout).
 */

import { useState } from 'react';
import { Avatar, Button, Group, Skeleton, Stack, Text, useMantineColorScheme } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconBrandDiscord, IconLogout } from '@tabler/icons-react';
import { useLocation } from 'react-router-dom';

import { useDelayedFlag, type SidebarDiscordSession } from '@/hooks';
import { getDiscordLoginUrl, logoutDiscordSession } from '@/api/auth';
import { toApiError } from '@/api/errors';
import { removePushDevice } from '@/api/push';
import { endpointId, getExistingSubscription } from '@/lib/push';
import { internalNavPath } from '@/lib/internalNavPath';

/** Longest logout waits for notification cleanup before continuing anyway. */
const PUSH_CLEANUP_TIMEOUT_MS = 3_000;

/**
 * Best-effort: stop reminder notifications in this browser before logging out, so whoever uses it
 * next doesn't get them. Never throws; true when this browser had notifications on.
 */
async function releaseThisBrowserPush(): Promise<boolean> {
  try {
    const subscription = await getExistingSubscription();
    if (!subscription) return false;
    try {
      await removePushDevice(await endpointId(subscription.endpoint));
    } catch {
      // The server also drops devices once their push service reports them gone.
    }
    await subscription.unsubscribe().catch(() => false);
    return true;
  } catch {
    // Never block logout.
    return false;
  }
}

interface DiscordSidebarCardProps {
  session: SidebarDiscordSession;
  /** Tighter layout when the viewport is short. */
  compact?: boolean;
}

export function DiscordSidebarCard({ session, compact = false }: DiscordSidebarCardProps) {
  const { colorScheme } = useMantineColorScheme();
  const location = useLocation();
  const showLoadingSkeleton = useDelayedFlag(session.status === 'loading', 150);
  const iconProps = {
    size: 18,
    stroke: 1.5,
    style: {
      color:
        colorScheme === 'light'
          ? 'var(--mantine-color-black)'
          : 'var(--mantine-color-white)',
      flexShrink: 0,
    } as const,
  };
  const [loggingOut, setLoggingOut] = useState(false);

  if (session.status === 'loading' && showLoadingSkeleton) {
    return <Skeleton height={compact ? 40 : 52} radius="sm" />;
  }

  if (session.status === 'loading') {
    return <div style={{ height: compact ? 36 : 52 }} />;
  }

  if (session.status === 'guest') {
    return (
      <Button
        component="a"
        // Come back to this page (and its filters) after signing in.
        href={getDiscordLoginUrl(internalNavPath(location.pathname, location.search))}
        size={compact ? 'sm' : 'md'}
        fullWidth
        color="indigo"
        variant="filled"
        leftSection={<IconBrandDiscord size={14} />}
        style={{ textDecoration: 'none' }}
        styles={{ root: { textDecoration: 'none' } }}
      >
        Login with Discord
      </Button>
    );
  }

  const { username, displayName, avatarUrl } = session;
  const shownName = displayName || username;
  const titleName = shownName || 'Discord';

  const handleLogout = async () => {
    if (loggingOut) return;
    setLoggingOut(true);
    const pushReleased = await Promise.race([
      releaseThisBrowserPush(),
      new Promise<boolean>((resolve) => window.setTimeout(() => resolve(true), PUSH_CLEANUP_TIMEOUT_MS)),
    ]);
    try {
      await logoutDiscordSession();
    } catch (error) {
      // Still signed in: say so instead of reloading into the same session.
      setLoggingOut(false);
      const pushNote = pushReleased
        ? ' Reminder notifications may already be off in this browser; check the Reminders page if you stay signed in.'
        : '';
      notifications.show({
        color: 'red',
        title: 'Logout failed',
        message: `${toApiError(error).message}${pushNote}`,
      });
      return;
    }
    // Full refresh so the session and every page's data start clean.
    window.location.reload();
  };

  return (
    <Stack gap={compact ? 2 : 4}>
      <Group gap={6} wrap="nowrap" align="center">
        <Avatar
          size={compact ? 18 : 20}
          src={avatarUrl}
          // Decorative: the name is shown next to it.
          alt=""
          radius="xl"
          color="indigo"
          styles={{ placeholder: { backgroundColor: 'var(--mantine-color-dark-5)' } }}
        >
          <IconBrandDiscord {...iconProps} />
        </Avatar>
        <Text size={compact ? 'xs' : 'sm'} fw={600} lh={1.2} lineClamp={1}>
          {titleName}
        </Text>
      </Group>
      <Group justify="flex-start" gap={4}>
        <Button
          size="compact-xs"
          variant="subtle"
          color="gray"
          leftSection={<IconLogout size={12} />}
          loading={loggingOut}
          onClick={handleLogout}
        >
          Logout
        </Button>
      </Group>
    </Stack>
  );
}
