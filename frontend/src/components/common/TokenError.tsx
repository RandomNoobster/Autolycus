/**
 * Token Error Component
 *
 * Displayed when no token is present or token is invalid.
 */

import { Container, Title, Text, Stack, Alert } from '@mantine/core';
import { IconAlertTriangle, IconLock } from '@tabler/icons-react';

interface TokenErrorProps {
  type: 'missing' | 'expired' | 'invalid';
  message?: string;
  dataType?: 'raids' | 'builds' | 'damage';
  redirectPath?: string;
}

export function TokenError({ type, message, dataType = 'raids' }: TokenErrorProps) {
  
  const config = {
    missing: {
      title: 'Authentication Required',
      description:
        'This page requires a valid access token. You can generate one directly or use a Discord bot link.',
      icon: <IconLock size={48} />,
    },
    expired: {
      title: 'Link Expired',
      description:
        'Your access link has expired. Please generate a new token or request one from the Discord bot.',
      icon: <IconAlertTriangle size={48} />,
    },
    invalid: {
      title: 'Invalid Link',
      description:
        'The access link is invalid or has been tampered with. Please generate a new token.',
      icon: <IconAlertTriangle size={48} />,
    },
  };

  const { title, description, icon } = config[type];

  return (
    <Container size="sm" py="xl">
      <Stack align="center" gap="lg">
        <Alert
          variant="light"
          color="orange"
          title={title}
          icon={icon}
          radius="md"
          style={{ width: '100%' }}
        >
          <Stack gap="sm">
            <Text>{description}</Text>
            {message && (
              <Text size="sm" c="dimmed">
                Error: {message}
              </Text>
            )}
          </Stack>
        </Alert>

        <Stack gap="xs" align="center">
          <Title order={4}>How to access this page:</Title>
          <Text size="sm" c="dimmed" ta="center">
            <strong>Access via Discord Bot</strong>
            <br />
            1. Open Discord and go to a server with Autolycus bot
            <br />
            2. Use the appropriate slash command (e.g., /raids, /builds, /damage)
            <br />
            3. Click the link provided by the bot
          </Text>
        </Stack>
      </Stack>
    </Container>
  );
}
