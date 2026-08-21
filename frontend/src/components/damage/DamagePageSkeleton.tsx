/**
 * Placeholder layout while damage analysis loads or before nations are chosen.
 */

import { Box, Flex, Group, Paper, Skeleton, Stack } from '@mantine/core';

const CHART_BAR_HEIGHTS_PX = [52, 88, 41, 102, 67, 94, 48, 115, 73, 61, 84, 56];

function ChartSkeleton({ animate }: { animate: boolean }) {
  return (
    <Paper p="md" withBorder radius="md" pos="relative" style={{ overflow: 'hidden' }}>
      {animate ? (
        <Box
          pos="absolute"
          top={0}
          left={0}
          h="100%"
          w="35%"
          style={{
            background:
              'linear-gradient(90deg, transparent, rgba(255, 146, 43, 0.1), transparent)',
            animation: 'damage-skeleton-sheen 2.4s ease-in-out infinite',
            pointerEvents: 'none',
          }}
        />
      ) : null}
      <Skeleton height={18} width="42%" mb="lg" radius="sm" animate={animate} />
      <Group gap="lg" mb="xs" wrap="nowrap">
        <Group gap={6}>
          <Skeleton circle height={10} width={10} animate={animate} />
          <Skeleton height={10} width={72} radius="xl" animate={animate} />
        </Group>
        <Group gap={6}>
          <Skeleton circle height={10} width={10} animate={animate} />
          <Skeleton height={10} width={68} radius="xl" animate={animate} />
        </Group>
      </Group>
      <Flex align="flex-end" justify="space-between" gap={{ base: 6, sm: 8 }} h={200}>
        {CHART_BAR_HEIGHTS_PX.map((h, i) => (
          <Skeleton
            key={i}
            h={h}
            flex={1}
            miw={{ base: 8, sm: 10 }}
            radius="sm"
            animate={animate}
            style={{ alignSelf: 'flex-end' }}
          />
        ))}
      </Flex>
      <Group justify="space-between" mt="md" gap="xs">
        <Skeleton height={8} w="18%" radius="xl" animate={animate} />
        <Skeleton height={8} w="22%" radius="xl" animate={animate} />
        <Skeleton height={8} w="16%" radius="xl" animate={animate} />
      </Group>
    </Paper>
  );
}

function ScenarioTableSkeleton({ animate }: { animate: boolean }) {
  return (
    <Paper p="lg" withBorder radius="md" shadow="sm">
      <Skeleton height={24} width="58%" mb="lg" radius="sm" animate={animate} />
      <Stack gap={10}>
        <Group gap="sm" wrap="nowrap">
          <Skeleton height={14} flex={1} radius="sm" animate={animate} />
          <Skeleton height={14} w={56} radius="sm" animate={animate} />
          <Skeleton height={14} w={56} radius="sm" animate={animate} />
          <Skeleton height={14} w={56} radius="sm" animate={animate} />
        </Group>
        {Array.from({ length: 7 }, (_, i) => (
          <Group key={i} gap="sm" wrap="nowrap">
            <Skeleton height={14} flex={1} radius="sm" animate={animate} />
            <Skeleton height={14} w={56} radius="sm" animate={animate} />
            <Skeleton height={14} w={56} radius="sm" animate={animate} />
            <Skeleton height={14} w={56} radius="sm" animate={animate} />
          </Group>
        ))}
      </Stack>
    </Paper>
  );
}

export type DamagePageSkeletonVariant = 'full' | 'results';

export interface DamagePageSkeletonProps {
  /** When true, reserve space for the page title + subtitle (full-page loading). */
  showPageHeader?: boolean;
  /** Pulse/shimmer; use only while data is loading (not for static preview before submit). */
  animated?: boolean;
  /**
   * `full` — placeholder for the whole calculator (e.g. before nations are chosen).
   * `results` — chart + tables only (page chrome and nation fields stay real).
   */
  variant?: DamagePageSkeletonVariant;
}

export function DamagePageSkeleton({
  showPageHeader = false,
  animated = false,
  variant = 'full',
}: DamagePageSkeletonProps) {
  const resultsOnly = variant === 'results';

  return (
    <Stack gap="lg">
      {showPageHeader ? (
        <Stack gap="xs">
          <Skeleton height={34} w={{ base: '85%', sm: 320 }} radius="sm" animate={animated} />
          <Skeleton height={15} w={{ base: '100%', sm: '55%' }} radius="sm" animate={animated} />
        </Stack>
      ) : null}

      {!resultsOnly ? (
        <>
          <Group gap="xs" wrap="nowrap">
            <Skeleton height={36} w={108} radius="md" animate={animated} />
            <Skeleton height={36} w={124} radius="md" animate={animated} />
            <Skeleton height={36} w={88} radius="md" animate={animated} />
          </Group>

          <Skeleton height={14} maw={480} w="100%" radius="sm" animate={animated} />
        </>
      ) : null}

      <ChartSkeleton animate={animated} />

      <ScenarioTableSkeleton animate={animated} />
      <ScenarioTableSkeleton animate={animated} />
    </Stack>
  );
}
