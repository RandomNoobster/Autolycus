import { Alert, Button, Modal, Stack, Text, TextInput } from '@mantine/core';
import { IconBrandDiscord } from '@tabler/icons-react';
import { useMutation } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';

import { getDiscordLoginUrl, verifyDiscordLink } from '@/api/auth';
import { internalNavPath } from '@/lib/internalNavPath';
import type { ApiError } from '@/types';

/** Backend code for a Discord sign-in too old to confirm the current username. */
const REAUTH_REQUIRED_CODE = 'REAUTH_REQUIRED';

interface VerifyNationModalProps {
  opened: boolean;
  onClose: () => void;
  onVerified?: () => void;
}

function parseNationId(input: string): string | null {
  const trimmed = input.trim();
  const urlMatch = trimmed.match(/(?:nation\/id=|nation_id=)(\d+)/i);
  if (urlMatch) return urlMatch[1];
  if (/^\d+$/.test(trimmed)) return trimmed;
  return null;
}

export function VerifyNationModal({ opened, onClose, onVerified }: VerifyNationModalProps) {
  const [nationInput, setNationInput] = useState('');
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const location = useLocation();
  const needsReauth = errorCode === REAUTH_REQUIRED_CODE;

  const verifyMutation = useMutation({
    mutationFn: async () => {
      const parsed = parseNationId(nationInput);
      if (!parsed) {
        throw { message: 'Please provide a valid nation ID or nation link.' } as ApiError;
      }
      return verifyDiscordLink({ nationId: parsed });
    },
    onSuccess: (result) => {
      setErrorMessage(null);
      setErrorCode(null);
      setSuccessMessage(
        result.relinked
          ? 'Verification updated. Your Discord account is now linked to the new nation.'
          : 'Verification successful. Your nation is now linked to your Discord account.'
      );
      onVerified?.();
    },
    onError: (error: unknown) => {
      const apiError = error as ApiError;
      setSuccessMessage(null);
      setErrorMessage(apiError.message || 'Verification failed. Please try again.');
      setErrorCode(apiError.code || null);
    },
  });

  // Only depend on `opened`. The mutation object from useMutation is a new reference whenever
  // mutation state changes (e.g. after reset()), so listing it here caused an infinite loop.
  useEffect(() => {
    if (!opened) {
      setSuccessMessage(null);
      setErrorMessage(null);
      setErrorCode(null);
      verifyMutation.reset();
    }
  }, [opened, verifyMutation.reset]);

  function submitVerify(event?: React.FormEvent) {
    event?.preventDefault();
    if (verifyMutation.isPending) return;
    setSuccessMessage(null);
    setErrorMessage(null);
    setErrorCode(null);
    verifyMutation.mutate();
  }

  return (
    <Modal opened={opened} onClose={onClose} title="Verify Nation" centered>
      <Stack gap="sm">
        <Text size="sm" c="dimmed">
          Link your Discord account to your Politics & War nation to enable extra features.
        </Text>
        <form onSubmit={submitVerify}>
          <Stack gap="sm">
            <TextInput
              label="Nation ID"
              placeholder="Nation ID or nation link"
              value={nationInput}
              onChange={(event) => setNationInput(event.currentTarget.value)}
            />
            <Button type="submit" loading={verifyMutation.isPending}>
              Verify
            </Button>
          </Stack>
        </form>
        {successMessage && (
          <Alert color="green" variant="light" title="Verified">
            {successMessage}
          </Alert>
        )}
        {errorMessage && (
          <Alert
            color="red"
            variant="light"
            title={needsReauth ? 'Sign in again to verify' : 'Verification failed'}
          >
            <Stack gap="sm">
              <Text size="sm">{errorMessage}</Text>
              {needsReauth && (
                <Button
                  component="a"
                  href={getDiscordLoginUrl(internalNavPath(location.pathname, location.search))}
                  size="sm"
                  color="indigo"
                  variant="filled"
                  leftSection={<IconBrandDiscord size={18} />}
                >
                  Sign in again
                </Button>
              )}
            </Stack>
          </Alert>
        )}
      </Stack>
    </Modal>
  );
}
