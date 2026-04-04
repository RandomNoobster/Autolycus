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

/** Recharts reserves a fixed legend box; if stacked/wrapped rows exceed it, legend draws over content below the chart. */
const MOBILE_LEGEND_BASE = 44;
const MOBILE_LEGEND_PER_ROW = 30;

export function DamageChart({ data, title = 'Net Damage Comparison' }: DamageChartProps) {
  const isMobile = useMediaQuery('(max-width: 48em)', false, {
    getInitialValueInEffect: false,
  });

  const seriesCount = data.series.length;
  const mobileLegendHeight = isMobile
    ? Math.min(180, MOBILE_LEGEND_BASE + Math.max(0, seriesCount - 1) * MOBILE_LEGEND_PER_ROW)
    : 48;
  const chartHeight = isMobile
    ? 268 + (mobileLegendHeight - MOBILE_LEGEND_BASE)
    : 300;

  return (
    <Paper shadow="sm" p={{ base: 'xs', sm: 'md', lg: 'lg' }} radius="md" withBorder>
      <Title order={4} mb={{ base: 4, sm: 'md' }} fz={isMobile ? 'md' : 'lg'}>
        {title}
      </Title>
      <BarChart
        h={chartHeight}
        data={data.data}
        dataKey="attackType"
        series={data.series}
        tickLine="y"
        gridAxis="xy"
        withLegend
        legendProps={{
          verticalAlign: 'bottom',
          height: mobileLegendHeight,
          align: 'center',
          layout: 'horizontal',
          wrapperStyle: isMobile ? { paddingTop: 0, paddingBottom: 0 } : { paddingTop: 6 },
        }}
        barChartProps={{
          margin: isMobile
            ? { top: 2, right: 2, left: 2, bottom: 0 }
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
                  alignContent: 'flex-start',
                  columnGap: 'var(--mantine-spacing-sm)',
                  rowGap: 2,
                  width: '100%',
                  height: '100%',
                  /* Mantine default for bottom legend is padding-top: spacing-md — removes chart↔legend gap on mobile */
                  paddingTop: 0,
                  paddingBottom: 0,
                },
                legendItem: {
                  flex: '1 1 100%',
                  justifyContent: 'center',
                  minWidth: 0,
                  maxWidth: '100%',
                  padding: '2px var(--mantine-spacing-xs)',
                },
                legendItemName: {
                  textAlign: 'center',
                  whiteSpace: 'normal',
                  wordBreak: 'break-word',
                  lineHeight: 1.15,
                  margin: 0,
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
        <Text size="xs" c="dimmed" ta="center" mt="sm" px={4} style={{ lineHeight: 1.35 }}>
          {MOBILE_CHART_AXIS_HINT}
        </Text>
      )}
    </Paper>
  );
}
