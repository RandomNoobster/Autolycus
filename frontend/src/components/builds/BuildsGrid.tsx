/**
 * Builds Grid Component
 *
 * Displays all build templates in a responsive grid layout.
 * Handles continent-specific resource sorting and validation.
 */

import { Badge, Group, SimpleGrid, Title, Text, Stack } from '@mantine/core';

import type { BuildData } from '@/types';
import { BuildCard } from './BuildCard';
import { formatNumber } from '@/utils';

interface BuildsGridProps {
  builds: Record<string, BuildData>;
  resources: string[];
  land: number;
}

export function BuildsGrid({
  builds,
  resources,
  land,
}: BuildsGridProps) {
  const netIncomeKey = resources.find((resource) => resource === 'net income') ?? 'net income';
  const netIncomeBuild = builds[netIncomeKey] ?? builds['net income'] ?? Object.values(builds)[0];

  if (!netIncomeBuild) {
    return null;
  }

  return (
    <Stack gap="xl">
      <div>
        <Group justify="space-between" align="center" mb="md" wrap="wrap">
          <div>
            <Title order={2}>Best Build for Net Income</Title>
            <Text size="sm" c="dimmed">
              This build maximizes total net income across all resources at your selected settings.
            </Text>
          </div>
          <Badge variant="outline" color="gray">
            Land per city: {formatNumber(land)}
          </Badge>
        </Group>
        <SimpleGrid cols={{ base: 1 }} spacing="lg">
          <BuildCard
            key={netIncomeKey}
            resourceType="net income"
            build={netIncomeBuild}
            land={land}
            allBuilds={[]}
            isValid={true}
          />
        </SimpleGrid>
      </div>
    </Stack>
  );
}
