/**
 * "Delivery" card on the Reminders page: Discord DM and browser notification channels, DM status
 * with fix steps, push devices, and recent delivery problems.
 */

import { useState, type ReactNode } from 'react';
import {
  Alert,
  Badge,
  Box,
  Button,
  Collapse,
  Divider,
  Group,
  Loader,
  Paper,
  Stack,
  Switch,
  Text,
  ThemeIcon,
  Title,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  IconAlertTriangle,
  IconBellOff,
  IconBellRinging,
  IconBrandDiscord,
  IconChevronDown,
  IconChevronUp,
  IconInfoCircle,
  IconSend,
} from '@tabler/icons-react';

import { requestTestDm, updateReminderChannels } from '@/api';
import { toApiError } from '@/api/errors';
import { useNow, type PushSubscriptionController } from '@/hooks';
import { sameDeviceId } from '@/lib/push';
import {
  DM_STATE_BADGES,
  REMINDERS_QUERY_KEY,
  REMINDER_DELIVERY_QUERY_KEY,
  channelErrorMessage,
  describeProblem,
  dmFailureReasonText,
  formatRelativeTime,
  isTestDmInFlight,
  plural,
  testDmErrorMessage,
} from '@/lib/reminderDelivery';
import type { ApiError, ReminderChannels, ReminderDelivery, ReminderProblem } from '@/types';

import { DmFailureHelp } from './DmFailureHelp';
import { PushDeviceList } from './PushDeviceList';

/** Lines up row content with the text next to the 36px channel icon. */
const ROW_INDENT = { base: 0, xs: 48 };

interface ReminderDeliveryCardProps {
  delivery: ReminderDelivery | undefined;
  loading: boolean;
  error: ApiError | null;
  onRetry: () => void;
  push: PushSubscriptionController;
}

function ProblemLine({ problem, now }: { problem: ReminderProblem; now: number }) {
  const when = formatRelativeTime(problem.at, now);
  const codeLabel =
    problem.code == null
      ? null
      : problem.kind === 'push_failed'
        ? `error ${problem.code}`
        : `Discord error ${problem.code}`;
  const meta = [when, codeLabel].filter(Boolean).join(' · ');

  return (
    <Box component="li" style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
      <IconAlertTriangle
        size={16}
        stroke={1.8}
        color="var(--mantine-color-yellow-6)"
        style={{ flexShrink: 0, marginTop: 3 }}
      />
      <Text size="sm">
        {describeProblem(problem)}
        {meta ? (
          <Text span size="xs" c="dimmed">
            {' '}
            · {meta}
          </Text>
        ) : null}
      </Text>
    </Box>
  );
}

export function ReminderDeliveryCard({ delivery, loading, error, onRetry, push }: ReminderDeliveryCardProps) {
  const queryClient = useQueryClient();
  const now = useNow();
  const [channelNotice, setChannelNotice] = useState<string | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);

  const channelsMutation = useMutation({
    mutationFn: (channels: ReminderChannels) => updateReminderChannels(channels),
    onMutate: async (channels: ReminderChannels) => {
      await queryClient.cancelQueries({ queryKey: REMINDER_DELIVERY_QUERY_KEY });
      const previous = queryClient.getQueryData<ReminderDelivery>(REMINDER_DELIVERY_QUERY_KEY);
      if (previous) {
        queryClient.setQueryData<ReminderDelivery>(REMINDER_DELIVERY_QUERY_KEY, { ...previous, channels });
      }
      return { previous };
    },
    onSuccess: (res) => {
      queryClient.setQueryData<ReminderDelivery>(REMINDER_DELIVERY_QUERY_KEY, res.delivery);
      void queryClient.invalidateQueries({ queryKey: REMINDERS_QUERY_KEY });
    },
    onError: (err, _channels, onMutateResult) => {
      if (onMutateResult?.previous) {
        queryClient.setQueryData<ReminderDelivery>(REMINDER_DELIVERY_QUERY_KEY, onMutateResult.previous);
      }
      setChannelNotice(channelErrorMessage(toApiError(err)));
    },
  });

  const testDmMutation = useMutation({
    mutationFn: () => requestTestDm(),
    onSuccess: (res) => {
      queryClient.setQueryData<ReminderDelivery>(REMINDER_DELIVERY_QUERY_KEY, res.delivery);
      notifications.show({
        title: 'Test DM on its way',
        message: 'Open your DMs from Autolycus in Discord and click Got it.',
        color: 'blue',
      });
    },
    onError: (err) => {
      const apiError = toApiError(err);
      notifications.show({
        title: 'Test DM not sent',
        message: testDmErrorMessage(apiError),
        color: apiError.code === 'RATE_LIMITED' ? 'yellow' : 'red',
      });
    },
  });

  if (!delivery) {
    return (
      <Paper p="lg" withBorder radius="md">
        <Stack gap="sm">
          <Title order={3}>Delivery</Title>
          {loading ? (
            <Group gap="xs">
              <Loader size="xs" />
              <Text size="sm" c="dimmed">
                Loading how reminders reach you…
              </Text>
            </Group>
          ) : (
            <>
              <Text size="sm" c="dimmed">
                Couldn't load your delivery settings.{error?.message ? ` ${error.message}` : ''}
              </Text>
              <Group>
                <Button size="xs" variant="light" onClick={onRetry}>
                  Try again
                </Button>
              </Group>
            </>
          )}
        </Stack>
      </Paper>
    );
  }

  const { channels, dm, latestTestDm, push: pushStatus, recentProblems } = delivery;
  const deviceCount = pushStatus.deviceCount;
  const pushBroken = channels.webPush && deviceCount === 0;
  const ago = (iso: string | null) => {
    const relative = formatRelativeTime(iso, now);
    return relative ? ` ${relative}` : '';
  };

  const setChannel = (channel: keyof ReminderChannels, on: boolean) => {
    const next: ReminderChannels = { ...channels, [channel]: on };
    if (!next.discordDm && !next.webPush) {
      setChannelNotice(
        channel === 'discordDm'
          ? 'Keep at least one delivery method on. Turn on browser notifications first, then you can turn off Discord DMs.'
          : 'Keep at least one delivery method on. Turn on Discord DMs first, then you can turn off browser notifications.'
      );
      return;
    }
    if (channel === 'discordDm' && !on && pushBroken) {
      setChannelNotice(
        'No device can receive browser notifications yet, so turning off Discord DMs would leave reminders no way to reach you. Turn on notifications for a device first.'
      );
      return;
    }
    if (channel === 'webPush' && on && deviceCount === 0) {
      setChannelNotice('Turn on notifications for at least one device before switching browser notifications on.');
      return;
    }
    setChannelNotice(null);
    channelsMutation.mutate(next);
  };

  // Discord DM status
  const dmBadge = DM_STATE_BADGES[dm.state] ?? DM_STATE_BADGES.unknown;
  const testInFlight = isTestDmInFlight(delivery);
  const dmFailed = dm.state === 'failed';
  const testAwaitingConfirmation = latestTestDm?.state === 'sent' && !latestTestDm.confirmedAt;

  let dmStatus: ReactNode;
  if (testInFlight) {
    dmStatus = (
      <Group gap={6} wrap="nowrap">
        <Loader size={12} />
        <Text size="sm" c="dimmed">
          Sending your test DM…
        </Text>
      </Group>
    );
  } else if (dmFailed) {
    dmStatus = (
      <Text size="sm" c="red">
        Not delivered{ago(dm.lastFailureAt)}. {dmFailureReasonText(dm.reason)}
        {dm.code != null ? (
          <Text span size="xs" c="dimmed">
            {' '}
            (Discord error {dm.code})
          </Text>
        ) : null}
      </Text>
    );
  } else if (testAwaitingConfirmation) {
    dmStatus = (
      <Text size="sm">
        Sent — click{' '}
        <Text span fw={700}>
          Got it
        </Text>{' '}
        in the DM. Don't see it? Check Message Requests and its Spam tab in Discord.
      </Text>
    );
  } else if (dm.state === 'confirmed') {
    dmStatus = (
      <Text size="sm" c="dimmed">
        You clicked Got it{ago(dm.confirmedAt)}, so DMs from Autolycus reach you.
      </Text>
    );
  } else if (dm.state === 'ok') {
    dmStatus = (
      <Text size="sm" c="dimmed">
        Discord accepted the last DM{ago(dm.lastSuccessAt)}. To confirm you can see DMs, send a test DM and click Got it.
      </Text>
    );
  } else {
    dmStatus = (
      <Text size="sm" c="dimmed">
        Autolycus hasn't DMed you yet. Send a test DM to check that Discord lets it reach you.
      </Text>
    );
  }

  // Browser notifications on this device
  const showPushSwitch = pushStatus.configured || channels.webPush;
  let pushBody: ReactNode;
  if (!pushStatus.configured) {
    pushBody = (
      <Text size="sm" c="dimmed">
        Browser notifications aren't set up on this server.
      </Text>
    );
  } else if (push.support === 'ios-unsupported') {
    pushBody = (
      <Text size="sm" c="dimmed">
        Browser notifications aren't available on iPhone and iPad yet. Use Discord DMs.
      </Text>
    );
  } else if (push.support === 'unsupported') {
    pushBody = (
      <Text size="sm" c="dimmed">
        This browser can't show notifications. If you opened Autolycus from Discord, open the page in your regular
        browser.
      </Text>
    );
  } else if (push.permission === 'denied') {
    pushBody = (
      <Text size="sm" c="dimmed">
        Notifications are blocked for this site. To allow them, click the icon at the left of the address bar, open
        the site settings, set Notifications to Allow, then reload this page.
      </Text>
    );
  } else {
    pushBody = (
      <Stack gap="xs">
        <Group gap="xs">
          {push.isThisDeviceEnabled ? (
            <Button
              size="xs"
              variant="light"
              color="gray"
              leftSection={<IconBellOff size={14} />}
              loading={sameDeviceId(push.removingDeviceId, push.thisDeviceId)}
              onClick={push.disableThisDevice}
            >
              Turn off on this device
            </Button>
          ) : (
            <Button
              size="xs"
              variant="light"
              leftSection={<IconBellRinging size={14} />}
              loading={push.enabling}
              disabled={!push.keyReady || push.checkingThisDevice}
              onClick={push.enableThisDevice}
            >
              Enable on this device
            </Button>
          )}
          <Button
            size="xs"
            variant="subtle"
            leftSection={<IconSend size={14} />}
            loading={push.testing}
            disabled={deviceCount === 0}
            onClick={push.sendTest}
          >
            Send test push
          </Button>
        </Group>
        {push.keyError && !push.keyReady ? (
          <Text size="xs" c="red">
            Couldn't load notification settings from the server. Reload the page to try again.
          </Text>
        ) : null}
        <Text size="xs" c="dimmed">
          Phones can delay notifications to save battery — keep Discord DMs on for time-critical targets.
        </Text>
      </Stack>
    );
  }

  return (
    <Paper p="lg" withBorder radius="md">
      <Stack gap="lg">
        <Group justify="space-between" align="flex-start" wrap="wrap" gap="xs">
          <div>
            <Title order={3}>Delivery</Title>
            <Text size="sm" c="dimmed" mt="xs">
              Choose how reminders reach you: Discord DMs, browser notifications, or both.
            </Text>
          </div>
          {delivery.needsAttention ? (
            <Badge color="yellow" variant="light" size="lg" leftSection={<IconAlertTriangle size={14} />}>
              Needs attention
            </Badge>
          ) : null}
        </Group>

        {channelNotice ? (
          <Alert
            color="yellow"
            variant="light"
            radius="md"
            icon={<IconInfoCircle size={18} />}
            withCloseButton
            closeButtonLabel="Dismiss"
            onClose={() => setChannelNotice(null)}
          >
            {channelNotice}
          </Alert>
        ) : null}

        <Stack gap="sm">
          <Group justify="space-between" align="flex-start" wrap="nowrap" gap="md">
            <Group gap="sm" align="flex-start" wrap="nowrap" style={{ minWidth: 0 }}>
              <ThemeIcon size={36} radius="md" variant="light" color="indigo" style={{ flexShrink: 0 }}>
                <IconBrandDiscord size={20} stroke={1.5} />
              </ThemeIcon>
              <Stack gap={4} style={{ minWidth: 0 }}>
                <Group gap="xs" wrap="wrap">
                  <Text fw={600}>Discord DM</Text>
                  <Badge size="sm" variant="light" color={dmBadge.color}>
                    {dmBadge.label}
                  </Badge>
                </Group>
                {dmStatus}
              </Stack>
            </Group>
            <Switch
              checked={channels.discordDm}
              onChange={(event) => setChannel('discordDm', event.currentTarget.checked)}
              disabled={channelsMutation.isPending}
              aria-label="Send reminders as Discord DMs"
            />
          </Group>
          <Group gap="xs" pl={ROW_INDENT}>
            <Button
              size="xs"
              variant="light"
              color="indigo"
              leftSection={<IconSend size={14} />}
              loading={testDmMutation.isPending}
              disabled={testInFlight}
              onClick={() => testDmMutation.mutate()}
            >
              Send test DM
            </Button>
            {!dmFailed ? (
              <Button
                size="xs"
                variant="subtle"
                color="gray"
                rightSection={helpOpen ? <IconChevronUp size={14} /> : <IconChevronDown size={14} />}
                aria-expanded={helpOpen}
                onClick={() => setHelpOpen((open) => !open)}
              >
                Having trouble?
              </Button>
            ) : null}
          </Group>
          <Collapse in={dmFailed || helpOpen}>
            <Box pl={ROW_INDENT}>
              <DmFailureHelp reason={dm.reason} supportInviteUrl={delivery.supportInviteUrl} />
            </Box>
          </Collapse>
        </Stack>

        <Divider />

        <Stack gap="sm">
          <Group justify="space-between" align="flex-start" wrap="nowrap" gap="md">
            <Group gap="sm" align="flex-start" wrap="nowrap" style={{ minWidth: 0 }}>
              <ThemeIcon size={36} radius="md" variant="light" color="orange" style={{ flexShrink: 0 }}>
                <IconBellRinging size={20} stroke={1.5} />
              </ThemeIcon>
              <Stack gap={4} style={{ minWidth: 0 }}>
                <Group gap="xs" wrap="wrap">
                  <Text fw={600}>Browser notifications</Text>
                  {pushBroken ? (
                    <Badge size="sm" variant="light" color="red">
                      No devices
                    </Badge>
                  ) : deviceCount > 0 ? (
                    <Badge size="sm" variant="light" color="gray">
                      {plural(deviceCount, 'device')}
                    </Badge>
                  ) : null}
                </Group>
                {pushBroken ? (
                  <Text size="sm" c="red">
                    Browser notifications are on, but no device can receive them. Turn them on for a device, or switch
                    browser notifications off.
                  </Text>
                ) : null}
                {pushBody}
              </Stack>
            </Group>
            {showPushSwitch ? (
              <Switch
                checked={channels.webPush}
                onChange={(event) => setChannel('webPush', event.currentTarget.checked)}
                disabled={channelsMutation.isPending || (!channels.webPush && deviceCount === 0)}
                aria-label="Send reminders as browser notifications"
              />
            ) : null}
          </Group>
          {push.devicesError ? (
            <Text size="xs" c="red" pl={ROW_INDENT}>
              Couldn't load your devices. {push.devicesError.message}
            </Text>
          ) : null}
          {push.devices.length > 0 ? (
            <Box pl={ROW_INDENT}>
              <PushDeviceList
                devices={push.devices}
                thisDeviceId={push.thisDeviceId}
                removingDeviceId={push.removingDeviceId}
                onRemove={push.removeDevice}
                now={now}
              />
            </Box>
          ) : null}
        </Stack>

        {recentProblems.length > 0 ? (
          <>
            <Divider />
            <Stack gap="xs">
              <Text fw={600}>Recent problems</Text>
              <Box
                component="ul"
                m={0}
                p={0}
                style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}
              >
                {recentProblems.map((problem, index) => (
                  <ProblemLine
                    key={`${problem.at}-${problem.nationId}-${problem.kind}-${index}`}
                    problem={problem}
                    now={now}
                  />
                ))}
              </Box>
            </Stack>
          </>
        ) : null}
      </Stack>
    </Paper>
  );
}
