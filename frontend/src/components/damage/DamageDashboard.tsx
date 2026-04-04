/**
 * Damage Dashboard Component
 *
 * Full dashboard layout with chart and tables for damage analysis.
 */

import { Stack, Text, Paper, Tabs } from '@mantine/core';

import type { DamageResponse } from '@/types';
import { DamageChart } from './DamageChart';
import { DamageTable } from './DamageTable';
import { ScenarioAttackHeading } from './ScenarioAttackHeading';

interface DamageDashboardProps {
  data: DamageResponse;
}

export function DamageDashboard({ data }: DamageDashboardProps) {
  const { scenarios, chartData } = data;
  const scenarioModes = [
    {
      value: 'attack',
      label: 'Per Attack',
      description:
        'Compare direct damage per attack. Best for quick baseline comparisons.',
    },
    {
      value: 'resistance',
      label: 'Per Resistance',
      description:
        'Damage per resistance reduced. Useful for maximizing damage without beiging. This takes into account your chance of winning the attack; if you lose an attack, you still deal damage but you don\'t reduce the opponent\'s resistance.',
    },
    {
      value: 'map',
      label: 'Per MAP',
      description:
        'Damage per MAP spent. Useful when beiging as quickly as possible.',
    },
  ] as const;

  const getStatsForMode = (
    stats: typeof scenarios.nation1Attacks.attacker.stats,
    mode: (typeof scenarioModes)[number]['value']
  ) => {
    if (mode === 'resistance') return stats.perResistance;
    if (mode === 'map') return stats.perMap;
    return stats.perAttack;
  };

  const buildChartData = (mode: (typeof scenarioModes)[number]['value']) => {
    const nation1Name = scenarios.nation1Attacks.attacker.info.nationName;
    const nation2Name = scenarios.nation2Attacks.attacker.info.nationName;
    const nation1Stats = getStatsForMode(scenarios.nation1Attacks.attacker.stats, mode);
    const nation2Stats = getStatsForMode(scenarios.nation2Attacks.attacker.stats, mode);
    const nation2Lookup = new Map(nation2Stats.map((row) => [row.attackType, row]));

    const data = nation1Stats.map((row) => ({
      attackType: row.label,
      [nation1Name]: row.netDamage,
      [nation2Name]: nation2Lookup.get(row.attackType)?.netDamage ?? 0,
    }));

    return {
      data,
      series: chartData.netDamageComparison?.series ?? [
        { name: nation1Name, color: 'blue.6' },
        { name: nation2Name, color: 'red.6' },
      ],
    };
  };

  return (
    <Stack gap="lg">
      <Text size="sm" c="dimmed">
        Use the tabs to switch between per-attack (default), per-resistance, and per-MAP
        views. Positive net damage is better; negative means the opponent would do more damage.
      </Text>

      <Tabs defaultValue="attack">
        <Tabs.List>
          {scenarioModes.map((mode) => (
            <Tabs.Tab key={mode.value} value={mode.value}>
              {mode.label}
            </Tabs.Tab>
          ))}
        </Tabs.List>

        {scenarioModes.map((mode) => (
          <Tabs.Panel key={mode.value} value={mode.value}>
            <Stack gap="lg" mt="md">
              <Text size="sm" c="dimmed">
                {mode.description}
              </Text>
              <DamageChart
                data={buildChartData(mode.value)}
                title={`Net Damage Comparison (${mode.label})`}
              />

              {[scenarios.nation1Attacks, scenarios.nation2Attacks].map((scenario) => (
                <Paper key={scenario.attacker.info.id} shadow="sm" p="lg" radius="md" withBorder>
                  <ScenarioAttackHeading
                    attacker={scenario.attacker.info}
                    defender={scenario.defender.info}
                    nation1Id={data.nations.nation1.id}
                  />
                  <DamageTable
                    attackerName={scenario.attacker.info.nationName}
                    defenderName={scenario.defender.info.nationName}
                    attackerNationId={scenario.attacker.info.id}
                    defenderNationId={scenario.defender.info.id}
                    nation1Id={data.nations.nation1.id}
                    attackerData={getStatsForMode(scenario.attacker.stats, mode.value)}
                    defenderData={getStatsForMode(scenario.defender.stats, mode.value)}
                  />
                </Paper>
              ))}
            </Stack>
          </Tabs.Panel>
        ))}
      </Tabs>
    </Stack>
  );
}
