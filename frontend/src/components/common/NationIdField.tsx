import { Button, Group, Loader, Stack, TextInput, Alert } from '@mantine/core';
import { IconAlertCircle, IconCheck } from '@tabler/icons-react';
import type { ButtonProps, GroupProps, MantineSize, TextInputProps } from '@mantine/core';
import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';

interface NationIdFieldProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  label?: ReactNode;
  description?: ReactNode;
  placeholder?: string;
  size?: MantineSize;
  buttonLabel: string;
  buttonIcon?: ReactNode;
  buttonDisabled?: boolean;
  loading?: boolean;
  layout?: 'row' | 'column';
  inputProps?: Omit<TextInputProps, 'value' | 'onChange' | 'label' | 'description'>;
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
  loading = false,
  layout = 'row',
  inputProps,
  buttonProps,
  groupProps,
  errorMessage,
  warningMessage,
  successMessage,
}: NationIdFieldProps) {
  const [showSuccess, setShowSuccess] = useState(false);

  // Show success state briefly when successMessage changes to a truthy value
  useEffect(() => {
    if (successMessage) {
      setShowSuccess(true);
      const timer = setTimeout(() => setShowSuccess(false), 2500);
      return () => clearTimeout(timer);
    }
    setShowSuccess(false);
  }, [successMessage]);

  const inputStyle = layout === 'row'
    ? { flex: 1, minWidth: 200, ...(inputProps?.style ?? {}) }
    : inputProps?.style;

  const buttonDisabledState = loading || buttonDisabled || buttonProps?.disabled;
  const buttonSize = buttonProps?.size ?? size;

  const isSuccess = showSuccess && !loading && !errorMessage;

  const textInput = (
    <TextInput
      value={value}
      onChange={(event) => onChange(event.currentTarget.value)}
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
      onClick={onSubmit}
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
        <Alert icon={<IconAlertCircle size={16} />} color="yellow" variant="light" style={{ flexBasis: '100%' }}>
          {warningMessage}
        </Alert>
      )}
    </Group>
  );
}
