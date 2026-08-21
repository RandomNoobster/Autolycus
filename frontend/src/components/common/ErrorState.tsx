/**
 * Error State Component
 */

import { Alert, Button, Stack, Text } from '@mantine/core';
import { IconAlertCircle, IconRefresh } from '@tabler/icons-react';

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export function ErrorState({
  title = 'Error',
  message,
  onRetry,
}: ErrorStateProps) {
  return (
    <Alert
      variant="light"
      color="red"
      title={title}
      icon={<IconAlertCircle />}
      radius="md"
    >
      <Stack gap="sm">
        <Text>{message}</Text>
        {onRetry && (
          <Button
            variant="light"
            color="red"
            size="sm"
            leftSection={<IconRefresh size={16} />}
            onClick={onRetry}
          >
            Try Again
          </Button>
        )}
      </Stack>
    </Alert>
  );
}
