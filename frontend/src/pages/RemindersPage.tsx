import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Container,
  Group,
  Image,
  List,
  Loader,
  NumberInput,
  Stack,
  Table,
  Text,
  TextInput,
  ThemeIcon,
  Title,
  Transition,
  useMantineColorScheme,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { IconBell, IconBrandDiscord, IconClock, IconCloudOff, IconSword } from '@tabler/icons-react';

import { addReminder, fetchReminders, removeReminder, updateReminderConfig } from '@/api';
import { isBackendUnreachableError, toApiError } from '@/api/errors';
import { getDiscordLoginUrl } from '@/api/auth';
import type { ApiError, ReminderNation } from '@/types';

const REMINDER_ROW_ENTER_MS = 280;

function ReminderTableRow({
  reminder,
  animateEnter,
  removePending,
  onRemove,
  onEnterAnimationEnd,
}: {
  reminder: ReminderNation;
  animateEnter: boolean;
  removePending: boolean;
  onRemove: () => void;
  onEnterAnimationEnd: () => void;
}) {
  const [mounted, setMounted] = useState(!animateEnter);

  useEffect(() => {
    if (!animateEnter) return;
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, [animateEnter]);

  return (
    <Transition
      keepMounted
      mounted={mounted}
      transition="fade-up"
      duration={REMINDER_ROW_ENTER_MS}
      timingFunction="cubic-bezier(0.4, 0, 0.2, 1)"
      onEntered={() => {
        if (animateEnter) onEnterAnimationEnd();
      }}
    >
      {(styles) => (
        <Table.Tr style={styles}>
          <Table.Td>
            <a href={`https://politicsandwar.com/nation/id=${reminder.nationId}`} target="_blank" rel="noreferrer">
              {reminder.nationName} ({reminder.nationId})
            </a>
          </Table.Td>
          <Table.Td>{reminder.leaderName}</Table.Td>
          <Table.Td>{reminder.beigeTurns}</Table.Td>
          <Table.Td>{reminder.vacationModeTurns}</Table.Td>
          <Table.Td>
            <Button size="xs" variant="light" color="red" loading={removePending} onClick={onRemove}>
              Delete
            </Button>
          </Table.Td>
        </Table.Tr>
      )}
    </Transition>
  );
}

function isDiscordSignInNeeded(error: ApiError): boolean {
  if (error.code === 'AUTH_REQUIRED' || error.code === 'TOKEN_MISSING') return true;
  const msg = (error.message || '').toLowerCase();
  return msg.includes('discord') && (msg.includes('sign in') || msg.includes('log in'));
}

/** Canonical display/storage order: furthest before exit → closest (descending minutes). */
function sortReminderOffsets(minutes: number[]): number[] {
  return [...minutes].sort((a, b) => b - a);
}

function formatOffsetConfig(minutes: number[]): string {
  return sortReminderOffsets(minutes).join(', ');
}

function parseOffsetList(raw: string): number[] | null {
  const tokens = raw
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean);
  if (!tokens.length) return null;
  const values = tokens.map((token) => Number(token));
  if (values.some((v) => !Number.isInteger(v) || v <= 0)) return null;
  return sortReminderOffsets(Array.from(new Set(values)));
}

function minutePhrase(n: number): string {
  return n === 1 ? '1 minute' : `${n} minutes`;
}

/** e.g. "60 minutes and 30 minutes before exit" */
function formatOffsetsHumanReadable(minutes: number[]): string {
  const sorted = sortReminderOffsets(minutes);
  if (sorted.length === 0) return '';
  const parts = sorted.map(minutePhrase);
  if (parts.length === 1) return `${parts[0]} before exit`;
  if (parts.length === 2) return `${parts[0]} and ${parts[1]} before exit`;
  return `${parts.slice(0, -1).join(', ')}, and ${parts[parts.length - 1]} before exit`;
}

function RemindersApiUnavailable({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <Container size="md" py="xl">
      <Alert
        icon={<IconCloudOff size={22} />}
        title="API unavailable"
        color="red"
        variant="light"
        radius="md"
      >
        <Stack gap="md">
          <Text size="sm">
            {message}
          </Text>
          <Text size="xs" c="dimmed">
            This is not a sign-in problem — the app cannot talk to the Autolycus server. If you run API and frontend
            separately, start the Flask (or Docker) backend first.
          </Text>
          <Button variant="filled" color="red" onClick={onRetry}>
            Try again
          </Button>
        </Stack>
      </Alert>
    </Container>
  );
}

function RemindersSignInPromo() {
  const { colorScheme } = useMantineColorScheme();
  const isLight = colorScheme === 'light';
  const loginUrl = getDiscordLoginUrl('/reminders');

  return (
    <Container size="md" py="xl">
      <Card
        padding={0}
        radius="lg"
        withBorder
        style={{
          overflow: 'hidden',
          borderColor: isLight ? 'var(--mantine-color-indigo-2)' : 'var(--mantine-color-dark-4)',
          background: isLight
            ? 'linear-gradient(145deg, rgba(99, 102, 241, 0.06) 0%, rgba(249, 115, 22, 0.08) 50%, rgba(255, 255, 255, 0.95) 100%)'
            : 'linear-gradient(145deg, rgba(88, 101, 242, 0.12) 0%, rgba(249, 115, 22, 0.1) 45%, var(--mantine-color-dark-7) 100%)',
          boxShadow: isLight
            ? '0 20px 50px rgba(15, 23, 42, 0.08)'
            : '0 24px 60px rgba(0, 0, 0, 0.45)',
        }}
      >
        <Stack gap={0}>
          <Box
            px="xl"
            pt="xl"
            pb="md"
            style={{
              borderBottom: `1px solid ${isLight ? 'var(--mantine-color-gray-2)' : 'var(--mantine-color-dark-5)'}`,
            }}
          >
            <Group justify="space-between" align="flex-start" wrap="nowrap" gap="md">
              <Stack gap="xs" style={{ flex: 1, minWidth: 0 }}>
                <Group gap="sm">
                  <ThemeIcon
                    size={52}
                    radius="md"
                    variant="gradient"
                    gradient={{ from: 'indigo', to: 'orange', deg: 125 }}
                  >
                    <IconBell size={28} stroke={1.5} />
                  </ThemeIcon>
                  <div>
                    <Text size="xs" tt="uppercase" fw={700} c="dimmed" lts={1.2}>
                      Discord perk
                    </Text>
                    <Title order={2} style={{ lineHeight: 1.2 }}>
                      Beige exit reminders
                    </Title>
                  </div>
                </Group>
                <Text size="md" c="dimmed" maw={480}>
                  Get Discord DMs before nations leave beige or vacation mode. Pick your lead times, manage targets from
                  here or the raids table — same settings as the bot.
                </Text>
              </Stack>
              <Image
                src="/splash.webp"
                alt=""
                w={120}
                h={72}
                fit="contain"
                visibleFrom="sm"
                style={{ flexShrink: 0, opacity: isLight ? 0.92 : 0.85 }}
              />
            </Group>
          </Box>

          <Stack px="xl" py="lg" gap="lg">
            <List spacing="sm" size="sm" center>
              <List.Item
                icon={
                  <ThemeIcon color="indigo" variant="light" size={28} radius="md">
                    <IconClock size={16} />
                  </ThemeIcon>
                }
              >
                Choose multiple alert offsets (minutes before exit)
              </List.Item>
              <List.Item
                icon={
                  <ThemeIcon color="indigo" variant="light" size={28} radius="md">
                    <IconBell size={16} />
                  </ThemeIcon>
                }
              >
                Add or remove nations from one place
              </List.Item>
              <List.Item
                icon={
                  <ThemeIcon color="indigo" variant="light" size={28} radius="md">
                    <IconSword size={16} />
                  </ThemeIcon>
                }
              >
                Toggle reminders from the Raid Targets table too
              </List.Item>
            </List>

            <Button
              component="a"
              href={loginUrl}
              size="md"
              fullWidth
              color="indigo"
              variant="filled"
              leftSection={<IconBrandDiscord size={20} />}
            >
              Continue with Discord
            </Button>
            <Text size="xs" c="dimmed">
              We use Discord only to know which account owns your reminders — same login as raids.
            </Text>
          </Stack>
        </Stack>
      </Card>
    </Container>
  );
}

export function RemindersPage() {
  const queryClient = useQueryClient();
  const [nationIdInput, setNationIdInput] = useState<number | ''>('');
  const [offsetInput, setOffsetInput] = useState('');
  const [lastAddedNationId, setLastAddedNationId] = useState<number | null>(null);

  const remindersQuery = useQuery({
    queryKey: ['reminders'],
    queryFn: fetchReminders,
    retry: false,
  });

  const syncRaidsAndReminders = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['reminders'] }),
      queryClient.invalidateQueries({ queryKey: ['raids'] }),
    ]);
  };

  const addMutation = useMutation({
    mutationFn: (nationId: number) => addReminder({ nationId }),
    onSuccess: async (_data, nationId) => {
      notifications.show({ title: 'Reminder added', message: 'Target was added to beige reminders.', color: 'green' });
      setNationIdInput('');
      setLastAddedNationId(nationId);
      await syncRaidsAndReminders();
    },
    onError: (error: ApiError) => {
      notifications.show({ title: 'Add failed', message: error.message, color: 'red' });
    },
  });

  const removeMutation = useMutation({
    mutationFn: (nationId: number) => removeReminder(nationId),
    onSuccess: async () => {
      notifications.show({ title: 'Reminder removed', message: 'Target was removed from beige reminders.', color: 'blue' });
      await syncRaidsAndReminders();
    },
    onError: (error: ApiError) => {
      notifications.show({ title: 'Delete failed', message: error.message, color: 'red' });
    },
  });

  const updateConfigMutation = useMutation({
    mutationFn: (beigeAlertConfig: number[]) => updateReminderConfig({ beigeAlertConfig }),
    onSuccess: async (res) => {
      const ordered = sortReminderOffsets(res.beigeAlertConfig);
      setOffsetInput(formatOffsetConfig(ordered));
      notifications.show({
        title: 'Timing saved',
        message: `Reminders will trigger ${ordered.join(', ')} minutes before beige/VM exit (largest offset = earliest heads-up).`,
        color: 'green',
      });
      await syncRaidsAndReminders();
    },
    onError: (error: ApiError) => {
      notifications.show({ title: 'Save failed', message: error.message, color: 'red' });
    },
  });

  const configDisplay = useMemo(() => {
    const config = remindersQuery.data?.beigeAlertConfig ?? [15];
    return formatOffsetConfig(config);
  }, [remindersQuery.data?.beigeAlertConfig]);

  const timingPreview = useMemo(() => {
    const saved = sortReminderOffsets(remindersQuery.data?.beigeAlertConfig ?? [15]);
    const trimmed = offsetInput.trim();
    if (trimmed) {
      const draft = parseOffsetList(offsetInput);
      if (draft) {
        return { label: 'Preview' as const, human: formatOffsetsHumanReadable(draft) };
      }
    }
    return { label: 'Saved' as const, human: formatOffsetsHumanReadable(saved) };
  }, [offsetInput, remindersQuery.data?.beigeAlertConfig]);

  if (remindersQuery.isLoading) {
    return (
      <Container size="lg" py="md">
        <Group justify="center">
          <Loader />
        </Group>
      </Container>
    );
  }

  if (remindersQuery.isError) {
    const error = toApiError(remindersQuery.error);
    if (isDiscordSignInNeeded(error)) {
      return <RemindersSignInPromo />;
    }
    if (isBackendUnreachableError(error)) {
      return (
        <RemindersApiUnavailable
          message={error.message}
          onRetry={() => void remindersQuery.refetch()}
        />
      );
    }
    return (
      <Container size="lg" py="md">
        <Alert icon={<IconBell size={20} />} title="Could not load reminders" color="orange" variant="light">
          <Stack gap="sm">
            <Text size="sm" c="dimmed">
              Something went wrong on our side or your session expired.
            </Text>
            <Text size="sm">{error.message}</Text>
            <Group>
              <Button variant="light" color="orange" onClick={() => void remindersQuery.refetch()}>
                Try again
              </Button>
              <Button
                component="a"
                href={getDiscordLoginUrl('/reminders')}
                variant="subtle"
                leftSection={<IconBrandDiscord size={18} />}
              >
                Sign in with Discord
              </Button>
            </Group>
          </Stack>
        </Alert>
      </Container>
    );
  }

  const reminders = remindersQuery.data?.reminders ?? [];

  return (
    <Container size="lg" py="md">
      <Stack gap="md">
        <Group justify="space-between">
          <Group gap="xs">
            <IconBell size={20} />
            <Title order={2}>Beige Reminders</Title>
          </Group>
          <Badge variant="light">{reminders.length} active</Badge>
        </Group>

        <Card withBorder>
          <Stack gap="sm">
            <Title order={4}>Timing</Title>
            <Stack gap="xs">
              <Text size="sm" c="dimmed">
                For each nation on your active reminders list, you get Discord DMs at the times you set below.
              </Text>
              <Text size="sm" c="dimmed">
                You can enter a{' '}
                <Text component="span" fw={600} c="var(--mantine-color-text)">
                  comma-separated list
                </Text>{' '}
                of integers. Each value in the list is how many minutes{' '}
                <Text component="span" fw={600} c="var(--mantine-color-text)">
                  before a nation is expected to leave beige or vacation mode
                </Text>{' '}
                you want a DM to be sent. Example{' '}
                <Text component="span" ff="monospace" size="sm">
                  60, 30, 15
                </Text>{' '}
                → means you get three DMs: one hour, 30 minutes, and 15 minutes before exit.{' '}
                <Text component="span" fw={600} c="var(--mantine-color-text)">
                  One number is enough,
                </Text>{' '}
                 e.g.{' '}
                <Text component="span" ff="monospace" size="sm">
                  15
                </Text>{' '}
                for a single 15-minute warning. 
              </Text>
            </Stack>
            <TextInput
              label="Reminder lead times"
              description="Positive integers only. Spaces around commas are fine."
              placeholder={configDisplay}
              value={offsetInput}
              onChange={(e) => setOffsetInput(e.currentTarget.value)}
            />
            <Group>
              <Button
                loading={updateConfigMutation.isPending}
                onClick={() => {
                  const parsed = parseOffsetList(offsetInput);
                  if (!parsed) {
                    notifications.show({
                      title: 'Invalid timing',
                      message: 'Use positive integer minutes separated by commas.',
                      color: 'red',
                    });
                    return;
                  }
                  updateConfigMutation.mutate(parsed);
                }}
              >
                Save timing
              </Button>
              <Text size="sm" c="dimmed">
                {timingPreview.label}: {timingPreview.human}
              </Text>
            </Group>
          </Stack>
        </Card>

        <Card withBorder>
          <Stack gap="sm">
            <Title order={4}>Add reminder</Title>
            <Group align="end">
              <NumberInput
                label="Nation ID"
                placeholder="123456"
                hideControls
                value={nationIdInput}
                onChange={(v) => setNationIdInput(typeof v === 'number' ? v : '')}
              />
              <Button
                loading={addMutation.isPending}
                onClick={() => {
                  if (!nationIdInput || nationIdInput <= 0) {
                    notifications.show({ title: 'Invalid nation ID', message: 'Enter a valid numeric nation ID.', color: 'red' });
                    return;
                  }
                  addMutation.mutate(Number(nationIdInput));
                }}
              >
                Add
              </Button>
            </Group>
          </Stack>
        </Card>

        <Card withBorder>
          <Stack gap="sm">
            <Title order={4}>Active reminders</Title>
            {reminders.length === 0 ? (
              <Text c="dimmed" size="sm">No active reminders yet. Add one above or from the raids page.</Text>
            ) : (
              <Table striped highlightOnHover withTableBorder>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Nation</Table.Th>
                    <Table.Th>Leader</Table.Th>
                    <Table.Th>Beige turns</Table.Th>
                    <Table.Th>VM turns</Table.Th>
                    <Table.Th />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {reminders.map((reminder) => (
                    <ReminderTableRow
                      key={reminder.nationId}
                      reminder={reminder}
                      animateEnter={reminder.nationId === lastAddedNationId}
                      removePending={removeMutation.isPending}
                      onRemove={() => removeMutation.mutate(reminder.nationId)}
                      onEnterAnimationEnd={() => {
                        setLastAddedNationId((id) => (id === reminder.nationId ? null : id));
                      }}
                    />
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Stack>
        </Card>
      </Stack>
    </Container>
  );
}
