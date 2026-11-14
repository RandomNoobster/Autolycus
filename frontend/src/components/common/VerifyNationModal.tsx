import { Alert, Button, Modal, Stack, Text, TextInput } from '@mantine/core';
import { IconBrandDiscord } from '@tabler/icons-react';
import { useMutation } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';

import { getDiscordLoginUrl, verifyDiscordLink } from '@/api/auth';
import { ApiRequestError, toApiError } from '@/api/errors';
import { internalNavPath } from '@/lib/internalNavPath';
import { parseNationId } from '@/utils/nationId';

/**
 * Backend codes a Discord sign-in fixes: the session is gone (AUTH_REQUIRED), or the
 * sign-in is too old to confirm the current username (REAUTH_REQUIRED).
 */
const SIGN_IN_CODES = new Set(['AUTH_REQUIRED', 'REAUTH_REQUIRED']);

interface VerifyNationModalProps {
  opened: boolean;
  onClose: () => void;
  onVerified?: () => void;
}

export function VerifyNationModal({ opened, onClose, onVerified }: VerifyNationModalProps) {
  const [nationInput, setNationInput] = useState('');
  const location = useLocation();

  const verifyMutation = useMutation({
    mutationFn: async () => {
      const parsed = parseNationId(nationInput);
      if (!parsed) {
        throw new ApiRequestError({
          error: 'Invalid nation',
          message: 'Please provide a valid nation ID or nation link.',
          code: 'VALIDATION_ERROR',
        });
      }
      return verifyDiscordLink({ nationId: parsed });
    },
    // Runs even if the modal closed meanwhile: the link changed either way.
    onSuccess: () => onVerified?.(),
  });
  const { reset: resetVerify } = verifyMutation;

  // Messages come from the mutation's own state, which reset() detaches: a request that
  // settles after the modal closed can't leave its result behind for the next opening.
  const result = verifyMutation.isSuccess ? verifyMutation.data : null;
  const apiError = verifyMutation.isError ? toApiError(verifyMutation.error) : null;
  const signInCode = apiError && SIGN_IN_CODES.has(apiError.code) ? apiError.code : null;

  useEffect(() => {
    if (!opened) resetVerify();
  }, [opened, resetVerify]);

  function submitVerify(event?: React.FormEvent) {
    event?.preventDefault();
    if (verifyMutation.isPending) return;
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
        {result && (
          <Alert color="green" variant="light" title="Verified">
            {result.relinked
              ? 'Verification updated. Your Discord account is now linked to the new nation.'
              : 'Verification successful. Your nation is now linked to your Discord account.'}
          </Alert>
        )}
        {apiError && (
          <Alert
            color="red"
            variant="light"
            title={
              signInCode === 'REAUTH_REQUIRED'
                ? 'Sign in again to verify'
                : signInCode
                  ? 'Sign in to verify'
                  : 'Verification failed'
            }
          >
            <Stack gap="sm">
              <Text size="sm">{apiError.message || 'Verification failed. Please try again.'}</Text>
              {signInCode && (
                <Button
                  component="a"
                  href={getDiscordLoginUrl(internalNavPath(location.pathname, location.search))}
                  size="sm"
                  color="indigo"
                  variant="filled"
                  leftSection={<IconBrandDiscord size={18} />}
                >
                  {signInCode === 'REAUTH_REQUIRED' ? 'Sign in again' : 'Sign in with Discord'}
                </Button>
              )}
            </Stack>
          </Alert>
        )}
      </Stack>
    </Modal>
  );
}
