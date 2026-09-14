/**
 * Steps for getting Discord DMs from Autolycus working.
 */

import type { ReactNode } from 'react';
import { Badge, Box, Button, Group, Paper, Stack, Text, ThemeIcon } from '@mantine/core';
import { IconBrandDiscord, IconExternalLink } from '@tabler/icons-react';

import type { DmFailureReason } from '@/types';

interface DmFailureHelpProps {
  reason: DmFailureReason | null;
  supportInviteUrl: string;
}

interface HelpStep {
  title: string;
  details?: ReactNode;
}

export function DmFailureHelp({ reason, supportInviteUrl }: DmFailureHelpProps) {
  // Point at the step that fixes the last failure, when Discord told us why.
  const highlightedStep = reason === 'no_mutual_server' ? 0 : reason === 'dms_closed' ? 1 : -1;

  const steps: HelpStep[] = [
    {
      title: 'Join a server Autolycus is in',
      details: supportInviteUrl ? (
        <Button
          component="a"
          href={supportInviteUrl}
          target="_blank"
          rel="noopener noreferrer"
          size="xs"
          variant="light"
          color="indigo"
          leftSection={<IconBrandDiscord size={14} />}
          rightSection={<IconExternalLink size={12} />}
          w="fit-content"
        >
          Join the Autolycus server
        </Button>
      ) : null,
    },
    {
      title: 'Allow DMs from that server',
      details: (
        <>
          <Text size="xs" c="dimmed">
            Desktop: right-click the server icon → Privacy Settings → Direct Messages on.
          </Text>
          <Text size="xs" c="dimmed">
            Mobile: profile → gear → Content &amp; Social → Server Settings → choose the server → Direct messages
            on.
          </Text>
        </>
      ),
    },
    {
      title: 'Optional, for future servers',
      details: (
        <Text size="xs" c="dimmed">
          User Settings → Content &amp; Social → Social permissions → Direct messages on, and apply it to existing
          servers.
        </Text>
      ),
    },
    {
      title: "Unblock Autolycus from its profile, and finish the server's rules screen if it has one.",
    },
    {
      title: 'Press Send test DM again.',
      details: (
        <Text size="xs" c="dimmed">
          If it arrives but you can't see it, check Message Requests and its Spam tab, then Accept.
        </Text>
      ),
    },
  ];

  return (
    <Paper withBorder radius="md" p="md">
      <Stack gap="sm">
        <Text size="sm" fw={600}>
          Get Discord DMs working
        </Text>
        <Box
          component="ol"
          m={0}
          p={0}
          style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 'var(--mantine-spacing-xs)' }}
        >
          {steps.map((step, index) => {
            const highlighted = index === highlightedStep;
            return (
              <Box
                component="li"
                key={step.title}
                p={highlighted ? 'xs' : 0}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 'var(--mantine-spacing-sm)',
                  borderRadius: 'var(--mantine-radius-sm)',
                  ...(highlighted
                    ? {
                        border: '1px solid var(--mantine-color-orange-outline)',
                        backgroundColor: 'var(--mantine-color-orange-light)',
                      }
                    : {}),
                }}
              >
                <ThemeIcon
                  size={22}
                  radius="xl"
                  variant={highlighted ? 'filled' : 'light'}
                  color={highlighted ? 'orange' : 'gray'}
                  style={{ flexShrink: 0 }}
                >
                  <Text span size="xs" fw={700}>
                    {index + 1}
                  </Text>
                </ThemeIcon>
                <Stack gap={4} style={{ flex: 1, minWidth: 0 }}>
                  <Group gap="xs" wrap="wrap">
                    <Text size="sm" fw={highlighted ? 600 : 500}>
                      {step.title}
                    </Text>
                    {highlighted ? (
                      <Badge size="xs" variant="filled" color="orange">
                        Start here
                      </Badge>
                    ) : null}
                  </Group>
                  {step.details}
                </Stack>
              </Box>
            );
          })}
        </Box>
        <Text size="xs" c="dimmed">
          Friend requests and messaging the bot first don't help — Discord only allows DMs through a shared server.
        </Text>
      </Stack>
    </Paper>
  );
}
