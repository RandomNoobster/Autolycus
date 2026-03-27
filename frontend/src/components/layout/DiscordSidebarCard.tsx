/**
 * Discord session summary for the app sidebar (raid API token).
 */

import { useEffect, useState } from 'react';
import { Badge, Group, Skeleton, Stack, Text } from '@mantine/core';
import { IconBrandDiscord } from '@tabler/icons-react';

import type { SidebarDiscordSession } from '@/hooks';

const iconProps = {
  size: 18,
  stroke: 1.5,
  style: { color: 'var(--mantine-color-white)', flexShrink: 0 } as const,
};

function formatTimeLeft(expiresAtSec: number): string {
  const now = Math.floor(Date.now() / 1000);
  const sec = Math.max(0, expiresAtSec - now);
  if (sec < 60) return 'less than a minute';
  const days = Math.floor(sec / 86400);
  if (days >= 1) return `${days} day${days === 1 ? '' : 's'}`;
  const hours = Math.floor(sec / 3600);
  if (hours >= 1) return `${hours} hour${hours === 1 ? '' : 's'}`;
  const minutes = Math.floor(sec / 60);
  return `${minutes} minute${minutes === 1 ? '' : 's'}`;
}

function formatExpiryTime(expiresAtSec: number): string {
  return new Date(expiresAtSec * 1000).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

interface DiscordSidebarCardProps {
  session: SidebarDiscordSession;
}

export function DiscordSidebarCard({ session }: DiscordSidebarCardProps) {
  const [, setTick] = useState(0);
  useEffect(() => {
    if (session.status !== 'signed_in') return;
    const id = window.setInterval(() => setTick((t) => t + 1), 30_000);
    return () => clearInterval(id);
  }, [session.status]);

  if (session.status === 'loading') {
    return <Skeleton height={52} radius="sm" />;
  }

  if (session.status === 'guest') {
    return (
      <Stack gap={4}>
        <Group gap={6} wrap="nowrap" align="center">
          <IconBrandDiscord {...iconProps} />
          <Text size="sm" fw={600} lh={1.2}>
            Discord
          </Text>
        </Group>
        <Text size="xs" c="dimmed" lh={1.35}>
          Not signed in. Use the link from the Autolycus Discord bot to open Raid Targets and
          activate a session.
        </Text>
      </Stack>
    );
  }

  const { discordUserId, expiresAtSec } = session;

  return (
    <Stack gap={4}>
      <Group gap={6} wrap="nowrap" align="center">
        <IconBrandDiscord {...iconProps} />
        <Group gap={6} wrap="wrap" align="center">
          <Text size="sm" fw={600} lh={1.2}>
            Discord
          </Text>
          <Badge size="xs" variant="light" color="green">
            Signed in
          </Badge>
        </Group>
      </Group>
      <Stack gap={2}>
        <Text size="xs" c="dimmed" lh={1.35}>
          Account:{' '}
          <Text span size="xs" ff="monospace" c="var(--mantine-color-text)">
            {discordUserId}
          </Text>{' '}
          <Text span size="xs" c="dimmed">
            (Discord user ID)
          </Text>
        </Text>
        <Text size="xs" c="dimmed" lh={1.35}>
          Session ends in <strong>{formatTimeLeft(expiresAtSec)}</strong> (
          {formatExpiryTime(expiresAtSec)}).
        </Text>
      </Stack>
    </Stack>
  );
}
