/**
 * Damage Chart Component
 *
 * Bar chart visualization of net damage by attack type.
 */

import { Paper, Title } from '@mantine/core';
import { BarChart } from '@mantine/charts';

import type { ChartConfig } from '@/types';

interface DamageChartProps {
  data: ChartConfig;
  title?: string;
}

export function DamageChart({ data, title = 'Net Damage Comparison' }: DamageChartProps) {
  return (
    <Paper shadow="sm" p="lg" radius="md" withBorder>
      <Title order={4} mb="md">
        {title}
      </Title>
      <BarChart
        h={300}
        data={data.data}
        dataKey="attackType"
        series={data.series}
        tickLine="y"
        gridAxis="xy"
        withLegend
        legendProps={{ verticalAlign: 'bottom', height: 50 }}
        valueFormatter={(value) => `$${value.toLocaleString()}`}
        style={{ paddingLeft: '16px' }}
      />
    </Paper>
  );
}
