/**
 * Raid Filters sidebar controls.
 */

import { useEffect, useRef, useState } from 'react';
import { Anchor, Group, NumberInput, Paper, Select, Stack, Text, TextInput } from '@mantine/core';
import type { NumberInputProps } from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';

/**
 * Local text for an input whose committed value is `value`. Typing commits after a pause, so
 * one keystroke doesn't rewrite the URL, refilter every row and refetch the list; changes from
 * outside (reset, autofill, the table's column filter) replace the text.
 */
function useDebouncedCommit(
  value: string,
  onCommit: (next: string) => void,
  wait = 400
) {
  const [local, setLocal] = useState(value);
  const [debounced] = useDebouncedValue(local, wait);
  const committedRef = useRef(value);

  useEffect(() => {
    if (value !== committedRef.current) {
      committedRef.current = value;
      setLocal(value);
    }
  }, [value]);

  useEffect(() => {
    if (debounced !== committedRef.current) {
      committedRef.current = debounced;
      onCommit(debounced);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  return [local, setLocal] as const;
}

/** A NumberInput whose value commits after typing pauses. */
export function DebouncedNumberInput({
  value,
  onCommit,
  ...props
}: Omit<NumberInputProps, 'value' | 'onChange'> & {
  value: string;
  onCommit: (next: string) => void;
}) {
  const [local, setLocal] = useDebouncedCommit(value, onCommit);
  return (
    <NumberInput
      {...props}
      value={local}
      onChange={(val) => setLocal(val === undefined || val === null ? '' : String(val))}
    />
  );
}

/** The per-card "reset" control: a real button, so it is focusable and announced. */
export function ResetLink({ onClick }: { onClick: () => void }) {
  return (
    <Anchor component="button" type="button" size="xs" onClick={onClick}>
      reset
    </Anchor>
  );
}

export type PresetOrCustomValue = {
  mode: 'none' | 'preset' | 'custom';
  preset: string;
  custom: string;
};

/** A filter card with preset minimums, "none", and a custom value typed by the user. */
export function PresetOrCustomFilterCard({
  title,
  description,
  noneValue,
  defaultPreset,
  options,
  customLabel,
  placeholder,
  value,
  onChange,
}: {
  title: string;
  description: string;
  /** The Select value meaning "no minimum". */
  noneValue: string;
  /** Preset kept while the mode is none or custom. */
  defaultPreset: string;
  options: { value: string; label: string }[];
  customLabel: string;
  placeholder: string;
  value: PresetOrCustomValue;
  onChange: (next: PresetOrCustomValue) => void;
}) {
  const none: PresetOrCustomValue = { mode: 'none', preset: defaultPreset, custom: '' };
  const [custom, setCustom] = useDebouncedCommit(value.custom, (text) =>
    onChange({ ...value, mode: 'custom', custom: text })
  );

  return (
    <Paper withBorder radius="sm" p="sm">
      <Stack gap={6}>
        <Group gap="xs" justify="space-between">
          <Text size="sm" fw={600}>
            {title}
          </Text>
          {value.mode !== 'none' && <ResetLink onClick={() => onChange(none)} />}
        </Group>
        <Text size="xs" c="dimmed">
          {description}
        </Text>
        <Select
          size="sm"
          data={[
            { value: noneValue, label: 'No minimum' },
            ...options,
            { value: 'custom', label: customLabel },
          ]}
          value={value.mode === 'custom' ? 'custom' : value.mode === 'none' ? noneValue : value.preset}
          onChange={(val) => {
            if (!val || val === noneValue) {
              onChange(none);
            } else if (val === 'custom') {
              onChange({ mode: 'custom', preset: defaultPreset, custom: value.custom });
            } else {
              onChange({ mode: 'preset', preset: val, custom: '' });
            }
          }}
        />
        {value.mode === 'custom' && (
          <TextInput
            size="sm"
            placeholder={placeholder}
            value={custom}
            onChange={(e) => setCustom(e.currentTarget.value)}
          />
        )}
      </Stack>
    </Paper>
  );
}
