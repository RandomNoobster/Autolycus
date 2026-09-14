/**
 * Compact sidebar warning shown when reminders can't reach the signed-in user.
 */

import { Anchor, Group, Text } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import { useNavigate } from 'react-router-dom';

import { useReminderDelivery, type SidebarDiscordSession } from '@/hooks';

interface ReminderDeliveryIndicatorProps {
  session: SidebarDiscordSession;
  /** Called after navigating so the mobile drawer can close. */
  onNavigate?: () => void;
}

export function ReminderDeliveryIndicator({ session, onNavigate }: ReminderDeliveryIndicatorProps) {
  const navigate = useNavigate();
  const signedIn = session.status === 'signed_in';
  const { data: delivery } = useReminderDelivery({ enabled: signedIn, poll: false });

  if (!signedIn || !delivery?.needsAttention) return null;

  return (
    <Anchor
      href="/reminders"
      underline="hover"
      c="var(--mantine-color-yellow-light-color)"
      bg="var(--mantine-color-yellow-light)"
      px={8}
      py={4}
      style={{ borderRadius: 'var(--mantine-radius-sm)', display: 'block' }}
      onClick={(event) => {
        event.preventDefault();
        navigate('/reminders');
        onNavigate?.();
      }}
    >
      <Group gap={6} wrap="nowrap">
        <IconAlertTriangle size={14} stroke={1.8} style={{ flexShrink: 0 }} />
        <Text span size="xs" fw={600} lh={1.2}>
          Reminders can't reach you
        </Text>
      </Group>
    </Anchor>
  );
}
