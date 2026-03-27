/**
 * Token Request Page
 *
 * This page handles generating secure tokens for accessing protected resources.
 */

import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Container,
  Title,
  Text,
  Stack,
  Button,
  Paper,
  Group,
  ThemeIcon,
  Alert,
  Loader,
} from '@mantine/core';
import { IconShield, IconAlertCircle, IconCheck } from '@tabler/icons-react';
import { exchangeToken } from '@/api';
import { persistAccessTokenFromExchange } from '@/lib/accessTokenStorage';

type DataType = 'raids' | 'builds' | 'damage';

export function TokenRequestPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dataType = (searchParams.get('type') || 'raids') as DataType;
  const redirectPath = searchParams.get('redirect') || `/${dataType}`;
  const authCode = searchParams.get('code') || undefined;

  const dataTypeLabels: Record<DataType, string> = {
    raids: 'Raid Targets',
    builds: 'City Builds',
    damage: 'Damage Calculator',
  };

  const handleGenerateToken = async () => {
    setLoading(true);
    setError(null);

    try {
      if (!authCode) {
        setError('Missing authorization code. Please use the link from the Discord bot.');
        setLoading(false);
        return;
      }

      const response = await exchangeToken({
        code: authCode,
      });

      await persistAccessTokenFromExchange(response);

      // Redirect to the target page with the token
      const separator = redirectPath.includes('?') ? '&' : '?';
      navigate(`${redirectPath}${separator}token=${response.token}`);
    } catch (err: any) {
      setError(err.message || 'Failed to generate token. Please try again.');
      setLoading(false);
    }
  };

  // Auto-generate token on mount (optional behavior)
  useEffect(() => {
    const autoGenerate = searchParams.get('auto');
    if (autoGenerate === 'true') {
      handleGenerateToken();
    }
  }, []);

  return (
    <Container size="sm" py="xl">
      <Stack gap="xl" align="center">
        <ThemeIcon size={80} radius="xl" variant="light" color="green">
          <IconShield size={48} />
        </ThemeIcon>

        <Stack gap="sm" align="center" ta="center">
          <Title order={1}>Secure Access Required</Title>
          <Text size="lg" c="dimmed" maw={500}>
            You need a secure token to access {dataTypeLabels[dataType]}.
            Click below to generate one.
          </Text>
        </Stack>

        {error && (
          <Alert
            icon={<IconAlertCircle size={16} />}
            title="Error"
            color="red"
            w="100%"
          >
            {error}
          </Alert>
        )}

        <Paper withBorder shadow="sm" p="xl" w="100%">
          <Stack gap="md">
            <Group>
              <ThemeIcon size={24} variant="light" color="green">
                <IconCheck size={16} />
              </ThemeIcon>
              <Text size="sm">Token expires in 1 hour</Text>
            </Group>
            <Group>
              <ThemeIcon size={24} variant="light" color="green">
                <IconCheck size={16} />
              </ThemeIcon>
              <Text size="sm">Secure signed authentication</Text>
            </Group>
            <Group>
              <ThemeIcon size={24} variant="light" color="green">
                <IconCheck size={16} />
              </ThemeIcon>
              <Text size="sm">No login required</Text>
            </Group>
            {!authCode && (
              <Alert
                icon={<IconAlertCircle size={16} />}
                title="Missing authorization code"
                color="yellow"
                variant="light"
              >
                Please open this page using the link provided by the Discord bot.
              </Alert>
            )}
          </Stack>
        </Paper>

        <Button
          size="lg"
          leftSection={loading ? <Loader size="xs" color="white" /> : <IconShield size={20} />}
          onClick={handleGenerateToken}
          disabled={loading || !authCode}
          fullWidth
        >
          {loading ? 'Generating Token...' : 'Use Discord Link'}
        </Button>

        <Text size="xs" c="dimmed" ta="center" maw={400}>
          This link was issued by the Discord bot and is valid for a short time.
          Your token is cryptographically signed and cannot be forged.
        </Text>
      </Stack>
    </Container>
  );
}
