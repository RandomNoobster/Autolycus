import { Button, Group, Loader, TextInput, Alert } from '@mantine/core';
import { IconAlertCircle, IconCheck } from '@tabler/icons-react';
import type { MantineSize, TextInputProps } from '@mantine/core';
import type { KeyboardEvent, ReactNode } from 'react';
import { useEffect, useState } from 'react';

interface NationIdFieldProps {
  /** The current id. Typing stays local until submit. */
  value: string;
  onSubmit: (value: string) => void;
  /** Called when the user types, e.g. so a late prefill doesn't replace their text. */
  onEdit?: () => void;
  label?: ReactNode;
  placeholder?: string;
  size?: MantineSize;
  buttonLabel: string;
  buttonIcon?: ReactNode;
  /** Disable the button while the input still matches `value` (already loaded), unless that load failed. */
  disableWhenUnchanged?: boolean;
  loading?: boolean;
  inputProps?: Omit<TextInputProps, 'value' | 'onChange' | 'label' | 'onKeyDown'>;
  errorMessage?: string | null;
  warningMessage?: string | null;
  successMessage?: string | null;
}

export function NationIdField({
  value,
  onSubmit,
  onEdit,
  label,
  placeholder,
  size = 'sm',
  buttonLabel,
  buttonIcon,
  disableWhenUnchanged = false,
  loading = false,
  inputProps,
  errorMessage,
  warningMessage,
  successMessage,
}: NationIdFieldProps) {
  const [localValue, setLocalValue] = useState(value);
  const [showSuccess, setShowSuccess] = useState(false);

  // Sync when parent loads a nation / prefills (not on every keystroke).
  useEffect(() => {
    setLocalValue(value);
  }, [value]);

  useEffect(() => {
    if (successMessage) {
      setShowSuccess(true);
      const timer = setTimeout(() => setShowSuccess(false), 2500);
      return () => clearTimeout(timer);
    }
    setShowSuccess(false);
  }, [successMessage]);

  const trimmed = localValue.trim();
  // After a failed load the same id must stay submittable, so the user can retry it.
  const unchanged = disableWhenUnchanged && !errorMessage && trimmed === value.trim();
  const buttonDisabled = loading || !trimmed || unchanged;
  const isSuccess = showSuccess && !loading && !errorMessage;

  const handleSubmit = () => {
    if (buttonDisabled) return;
    onSubmit(localValue);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    handleSubmit();
  };

  return (
    <Group gap="sm" align="flex-end" wrap="wrap">
      <TextInput
        value={localValue}
        onChange={(event) => {
          setLocalValue(event.currentTarget.value);
          onEdit?.();
        }}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        label={label}
        size={size}
        error={errorMessage || undefined}
        {...inputProps}
        style={{ flex: 1, minWidth: 200, ...(inputProps?.style ?? {}) }}
      />
      <Button
        size={size}
        leftSection={loading ? <Loader size="xs" /> : isSuccess ? <IconCheck size={16} /> : buttonIcon}
        onClick={handleSubmit}
        color={isSuccess ? 'green' : undefined}
        variant={isSuccess ? 'filled' : undefined}
        disabled={buttonDisabled}
      >
        {loading ? 'Loading...' : isSuccess ? 'Loaded!' : buttonLabel}
      </Button>
      {warningMessage && (
        <Alert
          icon={<IconAlertCircle size={16} />}
          color="yellow"
          variant="light"
          style={{ flexBasis: '100%' }}
        >
          {warningMessage}
        </Alert>
      )}
    </Group>
  );
}
