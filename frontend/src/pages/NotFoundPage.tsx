/**
 * 404 Not Found Page
 */

import { Container, Title, Text, Stack, Button, ThemeIcon } from '@mantine/core';
import { useNavigate } from 'react-router-dom';
import { IconError404, IconHome } from '@tabler/icons-react';

export function NotFoundPage() {
  const navigate = useNavigate();

  return (
    <Container size="sm" py="xl">
      <Stack align="center" gap="lg" ta="center">
        <ThemeIcon size={120} radius="xl" variant="light" color="gray">
          <IconError404 size={80} />
        </ThemeIcon>
        
        <Title order={1}>Page Not Found</Title>
        
        <Text size="lg" c="dimmed" maw={400}>
          The page you're looking for doesn't exist or has been moved.
          If you followed a link from Discord, it may have expired.
        </Text>
        
        <Button
          size="lg"
          leftSection={<IconHome size={20} />}
          onClick={() => navigate('/')}
        >
          Go to Home
        </Button>
      </Stack>
    </Container>
  );
}
