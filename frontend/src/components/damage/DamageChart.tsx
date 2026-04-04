/**
 * Damage Chart Component
 *
 * Bar chart visualization of net damage by attack type.
 */

import { Paper, Text, Title } from '@mantine/core';
import { BarChart } from '@mantine/charts';
import { useMediaQuery } from '@mantine/hooks';

import type { ChartConfig } from '@/types';

const usdAxisTicks = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  notation: 'compact',
  compactDisplay: 'short',
  maximumFractionDigits: 0,
});

const MOBILE_CHART_AXIS_HINT =
  'Tap the chart to see which attack each bar is and how much damage it deals.';

interface DamageChartProps {
  data: ChartConfig;
  title?: string;
}

export function DamageChart({ data, title = 'Net Damage Comparison' }: DamageChartProps) {
  const isMobile = useMediaQuery('(max-width: 48em)', false, {
    getInitialValueInEffect: false,
  });

  return (
    <Paper shadow="sm" p={{ base: 'xs', sm: 'md', lg: 'lg' }} radius="md" withBorder>
      <Title order={4} mb={{ base: 4, sm: 'md' }} fz={isMobile ? 'md' : 'lg'}>
        {title}
      </Title>
      <BarChart
        h={isMobile ? 268 : 300}
        data={data.data}
        dataKey="attackType"
        series={data.series}
        tickLine="y"
        gridAxis="xy"
        withLegend
        legendProps={{
          verticalAlign: 'bottom',
          height: isMobile ? 56 : 48,
          align: 'center',
          layout: 'horizontal',
          wrapperStyle: isMobile ? { paddingTop: 2 } : { paddingTop: 6 },
        }}
        barChartProps={{
          margin: isMobile
            ? { top: 2, right: 2, left: 2, bottom: 2 }
            : { top: 8, right: 12, left: 8, bottom: 8 },
        }}
        valueFormatter={(value) => `$${value.toLocaleString()}`}
        yAxisProps={{
          tickFormatter: (value) => usdAxisTicks.format(Number(value)),
          width: isMobile ? 44 : 52,
          tick: {
            fontSize: isMobile ? 10 : 12,
            transform: isMobile ? 'translate(-2, 0)' : 'translate(-6, 0)',
            fill: 'currentColor',
          },
        }}
        xAxisProps={
          isMobile
            ? {
                tick: false,
                tickLine: false,
                axisLine: false,
              }
            : {
                tick: {
                  fontSize: 12,
                  transform: 'translate(0, 10)',
                  fill: 'currentColor',
                },
              }
        }
        styles={
          isMobile
            ? {
                legend: {
                  display: 'flex',
                  flexWrap: 'wrap',
                  justifyContent: 'center',
                  alignItems: 'flex-start',
                  columnGap: 'var(--mantine-spacing-sm)',
                  rowGap: 6,
                  width: '100%',
                },
                legendItem: {
                  flex: '1 1 100%',
                  justifyContent: 'center',
                  minWidth: 0,
                  maxWidth: '100%',
                },
                legendItemName: {
                  textAlign: 'center',
                  whiteSpace: 'normal',
                  wordBreak: 'break-word',
                  lineHeight: 1.25,
                },
              }
            : {
                legend: {
                  display: 'flex',
                  flexWrap: 'wrap',
                  justifyContent: 'center',
                  columnGap: 'var(--mantine-spacing-md)',
                  rowGap: 4,
                  width: '100%',
                },
              }
        }
      />
      {isMobile && (
        <Text size="xs" c="dimmed" ta="center" mt={6} px={4} style={{ lineHeight: 1.35 }}>
          {MOBILE_CHART_AXIS_HINT}
        </Text>
      )}
    </Paper>
  );
}
