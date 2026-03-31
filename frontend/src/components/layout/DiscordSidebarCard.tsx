/**
 * Discord session summary for the app sidebar (raid API token).
 */

import { useEffect, useState } from 'react';
import { Avatar, Button, Group, Skeleton, Stack, Text, useMantineColorScheme } from '@mantine/core';
import { IconBrandDiscord, IconLogout } from '@tabler/icons-react';

import { useDelayedFlag, type SidebarDiscordSession } from '@/hooks';
import { getDiscordLoginUrl, logoutDiscordSession } from '@/api/auth';

interface DiscordSidebarCardProps {
  session: SidebarDiscordSession;
}

export function DiscordSidebarCard({ session }: DiscordSidebarCardProps) {
  const { colorScheme } = useMantineColorScheme();
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
  const [, setTick] = useState(0);
  const [loggingOut, setLoggingOut] = useState(false);
  useEffect(() => {
    if (session.status !== 'signed_in') return;
    const id = window.setInterval(() => setTick((t) => t + 1), 30_000);
    return () => clearInterval(id);
  }, [session.status]);

  if (session.status === 'loading' && showLoadingSkeleton) {
    return <Skeleton height={52} radius="sm" />;
  }

  if (session.status === 'loading') {
    // Reserve space during short gated loads to prevent layout jumps.
    return <div style={{ height: 52 }} />;
  }

  if (session.status === 'guest') {
    return (
      <Stack gap={0}>
        <Button
          component="a"
          href={getDiscordLoginUrl('/raids')}
          size="md"
          fullWidth
          color="indigo"
          variant="filled"
          leftSection={<IconBrandDiscord size={14} />}
          style={{ textDecoration: 'none' }}
          styles={{
            root: {
              textDecoration: 'none',
            },
          }}
        >
          Login with Discord
        </Button>
      </Stack>
    );
  }

  const { username, displayName, avatarUrl } = session;
  const shownName = displayName || username;
  const titleName = shownName || 'Discord';

  const handleLogout = async () => {
    if (loggingOut) return;
    setLoggingOut(true);
    try {
      await logoutDiscordSession();
    } finally {
      // Force a full refresh so sidebar session state and protected UI update immediately.
      window.location.reload();
    }
  };

  return (
    <Stack gap={4}>
      <Group gap={6} wrap="nowrap" align="center">
        <Avatar
          size={20}
          src={avatarUrl}
          radius="xl"
          color="indigo"
          styles={{ placeholder: { backgroundColor: 'var(--mantine-color-dark-5)' } }}
        >
          <IconBrandDiscord {...iconProps} />
        </Avatar>
        <Text size="sm" fw={600} lh={1.2}>
          {titleName}
        </Text>
      </Group>
      <Stack gap={2}>
        <Group justify="flex-start" mt={4}>
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
    </Stack>
  );
}
