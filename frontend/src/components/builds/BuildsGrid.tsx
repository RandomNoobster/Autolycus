/**
 * Builds Grid Component
 *
 * Displays all build templates in a responsive grid layout.
 * Handles continent-specific resource sorting and validation.
 */

import { Badge, Group, Paper, SimpleGrid, Title, Text, Stack } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';

import type { BuildData, Continent, ResourceType, BuildsResponse } from '@/types';
import { BuildCard } from './BuildCard';
import { isResourceValid } from '@/utils/continents';
import { ResourceIcon } from '@/components/common';
import { formatNumber } from '@/utils';

interface BuildsGridProps {
  builds: Record<string, BuildData>;
  resources: string[];
  land: number;
  uniqueBuilds: BuildData[];
  continent: Continent;
  foodModifiers?: BuildsResponse['foodModifiers'];
}

export function BuildsGrid({
  builds,
  resources,
  land,
  uniqueBuilds,
  continent,
  foodModifiers,
}: BuildsGridProps) {
  // Separate valid and invalid resources based on continent
  const validResources = resources.filter((resource) =>
    isResourceValid(resource, continent)
  );
  const invalidResources = resources.filter(
    (resource) => !isResourceValid(resource, continent)
  );

  return (
    <Stack gap="xl">
      {/* Valid Builds Section */}
      {validResources.length > 0 && (
        <div>
          <Group justify="space-between" align="center" mb="md">
            <div>
              <Title order={2}>
                Optimal Builds
              </Title>
              <Text size="sm" c="dimmed">
                These builds are optimized for your selected continent and can produce all resources shown.
              </Text>
            </div>
            <Badge variant="outline" color="gray">
              Land per city: {formatNumber(land)}
            </Badge>
          </Group>
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3, xl: 4 }} spacing="lg">
            {validResources.map((resource) => (
              <BuildCard
                key={resource}
                resourceType={resource}
                build={builds[resource]}
                land={land}
                allBuilds={uniqueBuilds}
                isValid={true}
              />
            ))}
          </SimpleGrid>
        </div>
      )}

      {/* Invalid Builds Section */}
      {invalidResources.length > 0 && (
        <Paper withBorder radius="md" p="md">
          <Group gap="xs" mb="xs" align="center" wrap="wrap">
            <IconAlertTriangle size={18} color="orange" />
            <Title order={3}>Continent Resource Modifiers</Title>
          </Group>
          <Text size="sm" c="dimmed" mb="sm">
            These raws cannot be produced on your selected continent. Swap continents to use these templates.
          </Text>
          <Group gap="sm" wrap="wrap">
            {invalidResources.map((resource) => (
              <Paper key={resource} withBorder p="xs" radius="sm" shadow="xs">
                <Group gap={6} align="center">
                  <ResourceIcon resource={resource as ResourceType} showValue={false} size={18} />
                  <Text tt="capitalize" fw={600} size="sm">
                    {resource}
                  </Text>
                </Group>
              </Paper>
            ))}
          </Group>
          <Text size="xs" c="dimmed" mt="xs">
            Manufactured resources remain available everywhere; only raw resource slots are continent-locked.
          </Text>
          {foodModifiers && (
            <Paper withBorder p="sm" radius="sm" mt="md" bg="dark.6">
              <Group gap="xs" mb="xs" align="center">
                <ResourceIcon resource="food" showValue={false} size={20} />
                <Text fw={600} size="sm">Food Production Modifiers</Text>
              </Group>
              <Stack gap={4}>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">Seasonal:</Text>
                  <Text size="sm" fw={500}>{((foodModifiers.seasonal - 1) * 100).toFixed(1)}%</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">Radiation:</Text>
                  <Text size="sm" fw={500}>{((foodModifiers.radiationMultiplier - 1) * 100).toFixed(1)}%</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed" fw={600}>Combined:</Text>
                  <Text size="sm" fw={600}>{((foodModifiers.combinedFoodMultiplier - 1) * 100).toFixed(1)}%</Text>
                </Group>
              </Stack>
            </Paper>
          )}
        </Paper>
      )}
    </Stack>
  );
}
