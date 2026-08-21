/**
 * Builds Grid Component
 *
 * Displays all build templates in a responsive grid layout.
 * Handles continent-specific resource sorting and validation.
 */

import { SimpleGrid, Stack } from '@mantine/core';

import type { BuildData } from '@/types';
import { BuildCard } from './BuildCard';

interface BuildsGridProps {
  builds: Record<string, BuildData>;
  resources: string[];
  showDualIncome?: boolean;
}

export function BuildsGrid({ builds, resources, showDualIncome = false }: BuildsGridProps) {
  const netIncomeKey = resources.find((resource) => resource === 'net income') ?? 'net income';
  const netIncomeBuild = builds[netIncomeKey] ?? builds['net income'] ?? Object.values(builds)[0];

  if (!netIncomeBuild) {
    return null;
  }

  return (
    <Stack gap="xl">
      <div>
        <SimpleGrid cols={{ base: 1 }} spacing="lg">
          <BuildCard
            key={netIncomeKey}
            resourceType="net income"
            build={netIncomeBuild}
            allBuilds={[]}
            isValid={true}
            showDualIncome={showDualIncome}
          />
        </SimpleGrid>
      </div>
    </Stack>
  );
}
