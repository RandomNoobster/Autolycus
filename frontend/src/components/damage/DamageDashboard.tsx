/**
 * Damage Dashboard Component
 *
 * Full dashboard layout with chart and tables for damage analysis.
 */

import { Stack, Grid, Alert, Text, Anchor, Group, Title, Paper } from '@mantine/core';
import { IconInfoCircle } from '@tabler/icons-react';

import type { DamageResponse } from '@/types';
import { DamageChart } from './DamageChart';
import { DamageTable } from './DamageTable';

interface DamageDashboardProps {
  data: DamageResponse;
}

export function DamageDashboard({ data }: DamageDashboardProps) {
  const { nation1, nation2, chartData } = data;

  return (
    <Stack gap="lg">
      {/* Info Alert */}
      <Alert
        variant="light"
        color="red"
        title="Disclaimer"
        icon={<IconInfoCircle />}
        radius="md"
      >
        <Text size="sm">
          <strong>Disclaimer</strong> - This tool is designed to help you decide
          what attack to perform in order to burn as many enemy pixels as
          possible. Please note that you should not blindly do the attacks with
          the highest net damage, and that targeting enemy military forces is
          usually a better move.
        </Text>
        <Text size="sm" mt="xs">
          <strong>How to use</strong> - There are two sections, one for each
          nation. Click on column headers to sort by that metric. Use the tabs
          to switch between "Per Resistance" (when winning), "Per MAP" (when
          losing), and "Total" (reference values).
        </Text>
        <Text size="sm" mt="xs">
          The resources listed are consumed by the attacking nation. For net
          damage, higher (positive) is better. Negative net damage means the
          opponent would do more damage.
        </Text>
      </Alert>

      {/* Chart Section */}
      <DamageChart
        data={chartData.netDamageComparison}
        title="Net Damage Comparison by Attack Type"
      />

      {/* Nation 1 Section */}
      <Paper shadow="sm" p="lg" radius="md" withBorder>
        <Group mb="md">
          <Title order={3}>
            <Anchor
              href={`https://politicsandwar.com/nation/id=${nation1.info.id}`}
              target="_blank"
            >
              If {nation1.info.nationName} attacks:
            </Anchor>
          </Title>
        </Group>

        <Grid gutter="lg">
          <Grid.Col span={{ base: 12, xl: 6 }}>
            <DamageTable
              nationName={nation1.info.nationName}
              role="attacker"
              perResistance={nation1.attacks.perResistance}
              perMap={nation1.attacks.perMap}
              totalStats={nation1.attacks.totalStats}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, xl: 6 }}>
            <DamageTable
              nationName={nation2.info.nationName}
              role="defender"
              perResistance={nation2.attacks.perResistance.map((stat) => ({
                ...stat,
                netDamage: -stat.netDamage, // Invert for defender perspective
              }))}
              perMap={nation2.attacks.perMap.map((stat) => ({
                ...stat,
                netDamage: -stat.netDamage,
              }))}
              totalStats={nation2.attacks.totalStats.map((stat) => ({
                ...stat,
                netDamage: -stat.netDamage,
              }))}
            />
          </Grid.Col>
        </Grid>
      </Paper>

      {/* Nation 2 Section */}
      <Paper shadow="sm" p="lg" radius="md" withBorder>
        <Group mb="md">
          <Title order={3}>
            <Anchor
              href={`https://politicsandwar.com/nation/id=${nation2.info.id}`}
              target="_blank"
            >
              If {nation2.info.nationName} attacks:
            </Anchor>
          </Title>
        </Group>

        <Grid gutter="lg">
          <Grid.Col span={{ base: 12, xl: 6 }}>
            <DamageTable
              nationName={nation2.info.nationName}
              role="attacker"
              perResistance={nation2.attacks.perResistance}
              perMap={nation2.attacks.perMap}
              totalStats={nation2.attacks.totalStats}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, xl: 6 }}>
            <DamageTable
              nationName={nation1.info.nationName}
              role="defender"
              perResistance={nation1.attacks.perResistance.map((stat) => ({
                ...stat,
                netDamage: -stat.netDamage,
              }))}
              perMap={nation1.attacks.perMap.map((stat) => ({
                ...stat,
                netDamage: -stat.netDamage,
              }))}
              totalStats={nation1.attacks.totalStats.map((stat) => ({
                ...stat,
                netDamage: -stat.netDamage,
              }))}
            />
          </Grid.Col>
        </Grid>
      </Paper>
    </Stack>
  );
}
