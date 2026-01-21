/**
 * Build Card Component
 *
 * Displays a single city build template with:
 * - Resource production icons
 * - Stats (disease, pollution, crime, commerce)
 * - Copy build functionality
 * - Links to P&W pages
 */

import { useCallback, useState } from 'react';
import type { ReactNode } from 'react';
import {
  Card,
  Group,
  Stack,
  Text,
  Title,
  Button,
  Code,
  Badge,
  Grid,
  Tooltip,
  ActionIcon,
  CopyButton,
  Paper,
} from '@mantine/core';
import {
  IconCopy,
  IconCheck,
  IconExternalLink,
  IconChevronLeft,
  IconChevronRight,
  IconInfoCircle,
  IconBiohazard,
  IconBuildingFactory,
  IconShieldLock,
  IconShoppingCart,
  IconAlertTriangle,
} from '@tabler/icons-react';

import type { BuildData } from '@/types';
import { ResourceIcon } from '@/components/common';
import { formatCurrency, formatNumber, formatPercentage, getProfitColor } from '@/utils';

interface BuildCardProps {
  resourceType: string;
  build: BuildData;
  land: number;
  allBuilds?: BuildData[];
  isValid?: boolean;
}

export function BuildCard({
  resourceType,
  build,
  land,
  allBuilds = [],
  isValid = true,
}: BuildCardProps) {
  const [currentIndex, setCurrentIndex] = useState(0);

  // Sort builds by the current resource type
  const sortedBuilds = [...allBuilds].sort((a, b) => {
    const aValue = (a as unknown as Record<string, number>)[resourceType] ?? a.netIncome;
    const bValue = (b as unknown as Record<string, number>)[resourceType] ?? b.netIncome;
    return bValue - aValue;
  });

  const currentBuild = sortedBuilds[currentIndex] || build;
  const hasMultiple = sortedBuilds.length > 1;
  const upkeep = currentBuild.unitUpkeep;
  const upkeepModeLabel = upkeep?.mode === 'war' ? 'wartime' : 'peacetime';
  const upkeepLine = upkeep
    ? upkeep.included
      ? `Using ${upkeepModeLabel} unit upkeep of ${formatCurrency(upkeep.total ?? 0)} in the net income calculated below.`
      : 'Not including military upkeep in the net income calculated below.'
    : 'Upkeep data unavailable for this build.';

  const handlePrev = useCallback(() => {
    setCurrentIndex((prev) => Math.max(0, prev - 1));
  }, []);

  const handleNext = useCallback(() => {
    setCurrentIndex((prev) => Math.min(sortedBuilds.length - 1, prev + 1));
  }, [sortedBuilds.length]);

  const formatResourceLabel = (rs: string) => {
    return rs
      .replace('net income', 'Net Income')
      .replace(/^\w/, (c) => c.toUpperCase());
  };

  return (
    <Card
      shadow="sm"
      padding="lg"
      radius="md"
      withBorder
      style={{
        opacity: isValid ? 1 : 0.6,
        filter: isValid ? 'none' : 'grayscale(50%)',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <Stack gap="md" style={{ flex: 1 }}>
        {/* Header */}
        <Group justify="space-between" align="flex-start">
          <Group gap="xs" style={{ flex: 1, minWidth: 0 }}>
            <Title order={4} style={{ wordBreak: 'break-word', overflowWrap: 'break-word' }}>
              Best build for {formatResourceLabel(resourceType)}
            </Title>
            {!isValid && (
              <Tooltip label="This resource cannot be produced on your selected continent">
                <ActionIcon variant="subtle" size="sm" color="orange" style={{ cursor: 'help' }}>
                  <IconInfoCircle size={16} />
                </ActionIcon>
              </Tooltip>
            )}
          </Group>
          {hasMultiple && (
            <Badge variant="light" color="gray">
              #{currentIndex + 1}
            </Badge>
          )}
        </Group>

        {!isValid && (
          <Badge color="orange" variant="light" fullWidth>
            Invalid for selected continent
          </Badge>
        )}

        {/* Template Code */}
        <Paper bg="dark.8" p="xs" radius="sm">
          <Code
            block
            style={{
              fontSize: '0.75rem',
              maxHeight: '200px',
              overflow: 'auto',
              fontFamily: 'JetBrains Mono, Consolas, Monaco, monospace',
            }}
          >
            {currentBuild.template}
          </Code>
        </Paper>

        {/* Actions */}
        <Group gap="xs">
          <CopyButton value={currentBuild.template} timeout={2000}>
            {({ copied, copy }) => (
              <Button
                size="xs"
                variant={copied ? 'filled' : 'light'}
                color={copied ? 'green' : 'blue'}
                leftSection={copied ? <IconCheck size={14} /> : <IconCopy size={14} />}
                onClick={copy}
              >
                {copied ? 'Copied!' : 'Copy Build'}
              </Button>
            )}
          </CopyButton>
          <Button
            size="xs"
            variant="light"
            rightSection={<IconExternalLink size={14} />}
            component="a"
            href="https://politicsandwar.com/city/improvements/bulk-import/"
            target="_blank"
          >
            Bulk Import
          </Button>
        </Group>

        {/* Stats - Fixed height grid */}
        <Grid gutter="xs">
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <StatItem
              icon={<IconBiohazard size={18} />}
              label="Disease"
              value={currentBuild.diseaseRate ?? 0}
              realValue={currentBuild.realDiseaseRate}
              formatter={(val) => formatPercentage(val as number, 1)}
              tooltip="Disease rate affects population growth. Lower is better."
              capType="floor"
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <StatItem
              icon={<IconBuildingFactory size={18} />}
              label="Pollution"
              value={currentBuild.pollution ?? 0}
              realValue={currentBuild.realPollution}
              formatter={(val) => `${formatNumber(val as number)} pts`}
              tooltip="Pollution feeds into disease. Lower is better."
              capType="floor"
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <StatItem
              icon={<IconShieldLock size={18} />}
              label="Crime"
              value={currentBuild.crimeRate ?? 0}
              realValue={currentBuild.realCrimeRate}
              formatter={(val) => formatPercentage(val as number, 1)}
              tooltip="Crime reduces commerce. Lower is better."
              capType="floor"
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <StatItem
              icon={<IconShoppingCart size={18} />}
              label="Commerce"
              value={currentBuild.commerce ?? 0}
              realValue={currentBuild.realCommerce}
              formatter={(val) => formatPercentage(val as number, 1)}
              tooltip="Commerce boosts revenue. Higher is better."
              capType="ceiling"
            />
          </Grid.Col>
          <Grid.Col span={12}>
            <Paper p="xs" radius="sm" withBorder>
              <Stack gap={4}>
                <Group gap="xs" align="center" wrap="wrap">
                  <IconShieldLock size={18} />
                  <Text fw={600} size="sm">
                    MMR
                  </Text>
                  <Badge variant="light" color="gray">
                    {currentBuild.mmr ?? '0/0/0/0'}
                  </Badge>
                </Group>
                <Text size="sm" c="dimmed" style={{ lineHeight: 1.3 }}>
                  {upkeepLine}
                </Text>
              </Stack>
            </Paper>
          </Grid.Col>
        </Grid>

        {/* Net Income - Show both formatted and exact value */}
        <Paper
          p="xs"
          radius="sm"
          withBorder
          style={{
            borderColor: `var(--mantine-color-${getProfitColor(
              Number(currentBuild?.netIncome ?? currentBuild?.netCash ?? 0)
            )}-6)`,
          }}
        >
          <Stack gap={4}>
            <Text
              ta="center"
              fw={600}
              c={getProfitColor(Number(currentBuild?.netIncome ?? currentBuild?.netCash ?? 0))}
              style={{
                fontFamily: 'JetBrains Mono, Consolas, Monaco, monospace',
              }}
            >
              Net Income ≈ {formatCurrency(
                Number(currentBuild?.netIncome ?? currentBuild?.netCash ?? 0)
              )}
            </Text>
            <Text
              ta="center"
              size="xs"
              c="dimmed"
              style={{
                fontFamily: 'JetBrains Mono, Consolas, Monaco, monospace',
              }}
            >
              ${formatNumber(Number(currentBuild?.netIncome ?? currentBuild?.netCash ?? 0), 2)}
            </Text>
          </Stack>
        </Paper>

        {/* Resource Production */}
        <Paper p="sm" radius="sm" withBorder>
          <Grid gutter="xs">
            <Grid.Col span={4}>
              <ResourceIcon resource="aluminum" value={currentBuild.aluminum ?? 0} size={18} />
            </Grid.Col>
            <Grid.Col span={4}>
              <ResourceIcon resource="bauxite" value={currentBuild.bauxite ?? 0} size={18} />
            </Grid.Col>
            <Grid.Col span={4}>
              <ResourceIcon resource="coal" value={currentBuild.coal ?? 0} size={18} />
            </Grid.Col>
            <Grid.Col span={4}>
              <ResourceIcon resource="gasoline" value={currentBuild.gasoline ?? 0} size={18} />
            </Grid.Col>
            <Grid.Col span={4}>
              <ResourceIcon resource="iron" value={currentBuild.iron ?? 0} size={18} />
            </Grid.Col>
            <Grid.Col span={4}>
              <ResourceIcon resource="lead" value={currentBuild.lead ?? 0} size={18} />
            </Grid.Col>
            <Grid.Col span={4}>
              <ResourceIcon
                resource="money"
                value={Number(currentBuild?.netCash ?? currentBuild?.netIncome ?? 0)}
                size={18}
              />
            </Grid.Col>
            <Grid.Col span={4}>
              <ResourceIcon resource="munitions" value={currentBuild.munitions ?? 0} size={18} />
            </Grid.Col>
            <Grid.Col span={4}>
              <ResourceIcon resource="oil" value={currentBuild.oil ?? 0} size={18} />
            </Grid.Col>
            <Grid.Col span={4}>
              <ResourceIcon resource="food" value={currentBuild.food ?? 0} size={18} />
            </Grid.Col>
            <Grid.Col span={4}>
              <ResourceIcon resource="steel" value={currentBuild.steel ?? 0} size={18} />
            </Grid.Col>
            <Grid.Col span={4}>
              <ResourceIcon resource="uranium" value={currentBuild.uranium ?? 0} size={18} />
            </Grid.Col>
          </Grid>
        </Paper>

        {/* Navigation */}
        {hasMultiple && (
          <Group justify="space-between">
            <ActionIcon
              variant="light"
              onClick={handlePrev}
              disabled={currentIndex === 0}
            >
              <IconChevronLeft size={16} />
            </ActionIcon>
            <Text size="sm" c="dimmed">
              #{currentIndex + 1} of {sortedBuilds.length}
            </Text>
            <ActionIcon
              variant="light"
              onClick={handleNext}
              disabled={currentIndex >= sortedBuilds.length - 1}
            >
              <IconChevronRight size={16} />
            </ActionIcon>
          </Group>
        )}
      </Stack>
    </Card>
  );
}

interface StatItemProps {
  label: string;
  icon?: ReactNode;
  value: number | string;
  realValue?: number;
  formatter?: (value: number | string) => string;
  tooltip?: string;
  capType?: 'floor' | 'ceiling' | 'both';
}

function StatItem({ label, icon, value, realValue, formatter, tooltip, capType = 'both' }: StatItemProps) {
  const formattedValue = formatter ? formatter(value) : String(value);
  const numericValue = typeof value === 'number' ? value : undefined;
  
  // Determine if value was clamped to a boundary
  // For disease/crime/pollution: clamped means raw < 0 but displayed as 0 (floor)
  // For commerce: clamped means raw > max but displayed at max (ceiling)
  const hasCap = (() => {
    if (numericValue === undefined || realValue === undefined) return false;
    const epsilon = 0.01;
    const formattedRaw = formatter ? formatter(realValue) : String(realValue);
    const formattedShown = formatter ? formatter(numericValue) : String(numericValue);

    const canFloor = capType === 'floor' || capType === 'both';
    const canCeil = capType === 'ceiling' || capType === 'both';

    // Floor case: displayed value is 0, raw value is negative
    if (canFloor && numericValue === 0 && realValue < 0) return true;

    // Ceiling case: raw value exceeds displayed value AND rounding doesn't explain it
    if (canCeil && realValue > numericValue + epsilon && formattedRaw !== formattedShown) {
      return true;
    }

    return false;
  })();
  
  const capDirection = hasCap && realValue !== undefined && numericValue !== undefined
    ? (realValue > numericValue ? 'ceiling' : 'floor')
    : null;
  const formattedRaw = hasCap && realValue !== undefined
    ? formatter?.(realValue) ?? String(realValue)
    : null;

  const capNote = hasCap
    ? capDirection === 'ceiling'
      ? ` Raw calculation ${formattedRaw} but capped at the maximum allowed.`
      : ` Raw calculation ${formattedRaw} but capped at 0.`
    : '';

  const badge = hasCap ? (
    <Tooltip
      label={capNote.trim()}
      withArrow
    >
      <Badge
        size="xs"
        variant="light"
        color="blue"
        leftSection={<IconAlertTriangle size={12} />}
      >
        Capped
      </Badge>
    </Tooltip>
  ) : null;

  const content = (
    <Paper
      p="xs"
      radius="sm"
      withBorder
      style={{ cursor: tooltip ? 'help' : 'default', height: '100%' }}
    >
      <Stack gap={6} justify="center" style={{ minHeight: 64 }}>
        <Group gap="xs" align="center" wrap="nowrap">
          {icon}
          <Text fw={600} size="sm" style={{ wordBreak: 'break-word' }}>
            {label}
          </Text>
        </Group>
        <Group gap={6} align="center" wrap="wrap">
          <Text
            size="sm"
            style={{
              fontFamily: 'SF Mono, Monaco, Consolas, monospace',
            }}
          >
            {formattedValue}
          </Text>
          {badge}
        </Group>
      </Stack>
    </Paper>
  );

  if (tooltip) {
    const tooltipLabel = hasCap ? `${tooltip}${capNote}` : tooltip;
    return (
      <Tooltip label={tooltipLabel} multiline w={240}>
        <div>{content}</div>
      </Tooltip>
    );
  }

  return content;
}
