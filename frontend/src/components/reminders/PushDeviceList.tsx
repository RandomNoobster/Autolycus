/**
 * Devices registered for reminder notifications.
 */

import { Badge, Button, Group, Stack, Text } from '@mantine/core';
import { IconTrash } from '@tabler/icons-react';

import { sameDeviceId } from '@/lib/push';
import { formatLocalDate, formatRelativeTime, isLater } from '@/lib/reminderDelivery';
import type { PushDevice } from '@/types';

interface PushDeviceListProps {
  devices: PushDevice[];
  /** This browser's device id, when the server lists it. */
  thisDeviceId: string | null;
  removingDeviceId: string | null;
  onRemove: (deviceId: string) => void;
  now: number;
}

export function PushDeviceList({ devices, thisDeviceId, removingDeviceId, onRemove, now }: PushDeviceListProps) {
  if (devices.length === 0) return null;

  // This device first; otherwise keep the server's order.
  const ordered = [...devices].sort(
    (a, b) => Number(sameDeviceId(b.id, thisDeviceId)) - Number(sameDeviceId(a.id, thisDeviceId))
  );

  return (
    <Stack
      gap={0}
      style={{ border: '1px solid var(--mantine-color-default-border)', borderRadius: 'var(--mantine-radius-md)' }}
    >
      {ordered.map((device, index) => {
        const isThisDevice = sameDeviceId(device.id, thisDeviceId);
        const isRemoving = sameDeviceId(removingDeviceId, device.id);
        const lastAttemptFailed = isLater(device.lastFailureAt, device.lastSuccessAt);
        const label = device.label || 'Browser';
        return (
          <Group
            key={device.id}
            justify="space-between"
            wrap="nowrap"
            gap="sm"
            px="sm"
            py="xs"
            style={index > 0 ? { borderTop: '1px solid var(--mantine-color-default-border)' } : undefined}
          >
            <Stack gap={2} style={{ minWidth: 0 }}>
              <Group gap={6} wrap="wrap">
                <Text size="sm" fw={500}>
                  {label}
                </Text>
                {isThisDevice ? (
                  <Badge size="xs" variant="light" color="orange">
                    This device
                  </Badge>
                ) : null}
              </Group>
              <Text size="xs" c="dimmed">
                Added {formatLocalDate(device.createdAt)} ·{' '}
                {device.lastSuccessAt
                  ? `Last delivered ${formatRelativeTime(device.lastSuccessAt, now)}`
                  : 'Nothing delivered yet'}
              </Text>
              {lastAttemptFailed ? (
                <Text size="xs" c="red">
                  Last notification failed {formatRelativeTime(device.lastFailureAt, now)}
                </Text>
              ) : null}
            </Stack>
            <Button
              size="compact-xs"
              variant="subtle"
              color="red"
              leftSection={<IconTrash size={12} />}
              loading={isRemoving}
              disabled={removingDeviceId !== null && !isRemoving}
              onClick={() => onRemove(device.id)}
              aria-label={`Remove ${label}`}
            >
              Remove
            </Button>
          </Group>
        );
      })}
    </Stack>
  );
}
