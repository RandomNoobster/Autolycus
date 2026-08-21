/**
 * Loading State Component
 */

import { Center, Loader, Stack, Text } from '@mantine/core';

interface LoadingStateProps {
  message?: string;
}

export function LoadingState({ message = 'Loading...' }: LoadingStateProps) {
  return (
    <Center h="50vh">
      <Stack align="center" gap="md">
        <Loader size="lg" type="dots" />
        <Text c="dimmed">{message}</Text>
      </Stack>
    </Center>
  );
}
