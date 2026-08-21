import { Button, Group, Loader, Stack, TextInput, Alert } from '@mantine/core';
import { IconAlertCircle, IconCheck } from '@tabler/icons-react';
import type { ButtonProps, GroupProps, MantineSize, TextInputProps } from '@mantine/core';
import type { KeyboardEvent, ReactNode } from 'react';
import { useEffect, useState } from 'react';

interface NationIdFieldProps {
  value: string;
  /** Optional live parent sync. Prefer omitting this on heavy pages — typing stays local until submit. */
  onChange?: (value: string) => void;
  onSubmit: (value: string) => void;
  label?: ReactNode;
  description?: ReactNode;
  placeholder?: string;
  size?: MantineSize;
  buttonLabel: string;
  buttonIcon?: ReactNode;
  buttonDisabled?: boolean;
  /** Disable Load when the input still matches the controlled `value` (already loaded id). */
  disableWhenUnchanged?: boolean;
  loading?: boolean;
  layout?: 'row' | 'column';
  inputProps?: Omit<TextInputProps, 'value' | 'onChange' | 'label' | 'description' | 'onKeyDown'>;
  buttonProps?: Omit<ButtonProps, 'onClick' | 'leftSection' | 'children'>;
  groupProps?: Omit<GroupProps, 'children'>;
  errorMessage?: string | null;
  warningMessage?: string | null;
  successMessage?: string | null;
}

export function NationIdField({
  value,
  onChange,
  onSubmit,
  label,
  description,
  placeholder,
  size = 'sm',
  buttonLabel,
  buttonIcon,
  buttonDisabled = false,
  disableWhenUnchanged = false,
  loading = false,
  layout = 'row',
  inputProps,
  buttonProps,
  groupProps,
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
  const unchanged = disableWhenUnchanged && trimmed === value.trim();
  const buttonDisabledState =
    loading || buttonDisabled || !trimmed || unchanged || buttonProps?.disabled;
  const buttonSize = buttonProps?.size ?? size;
  const isSuccess = showSuccess && !loading && !errorMessage;

  const handleChange = (next: string) => {
    setLocalValue(next);
    onChange?.(next);
  };

  const handleSubmit = () => {
    if (buttonDisabledState) return;
    onSubmit(localValue);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    handleSubmit();
  };

  const inputStyle =
    layout === 'row' ? { flex: 1, minWidth: 200, ...(inputProps?.style ?? {}) } : inputProps?.style;

  const textInput = (
    <TextInput
      value={localValue}
      onChange={(event) => handleChange(event.currentTarget.value)}
      onKeyDown={handleKeyDown}
      placeholder={placeholder}
      label={label}
      description={description}
      size={size}
      error={errorMessage || undefined}
      {...inputProps}
      style={inputStyle}
    />
  );

  const button = (
    <Button
      size={buttonSize}
      leftSection={loading ? <Loader size="xs" /> : isSuccess ? <IconCheck size={16} /> : buttonIcon}
      onClick={handleSubmit}
      color={isSuccess ? 'green' : undefined}
      variant={isSuccess ? 'filled' : buttonProps?.variant}
      {...buttonProps}
      disabled={buttonDisabledState}
    >
      {loading ? 'Loading...' : isSuccess ? 'Loaded!' : buttonLabel}
    </Button>
  );

  if (layout === 'column') {
    return (
      <Stack gap="xs">
        {textInput}
        {button}
        {warningMessage && (
          <Alert icon={<IconAlertCircle size={16} />} color="yellow" variant="light">
            {warningMessage}
          </Alert>
        )}
      </Stack>
    );
  }

  return (
    <Group gap="sm" align="flex-end" wrap="wrap" {...groupProps}>
      {textInput}
      {button}
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
