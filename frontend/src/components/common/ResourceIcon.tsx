/**
 * Resource Icon Component
 *
 * Displays game resource icons with optional values.
 */

import { Group, Image, Text, Tooltip } from '@mantine/core';
import type { ResourceType } from '@/types';
import { formatMetric, formatNumber } from '@/utils';

// Resource icon URLs (hosted externally or locally)
const RESOURCE_ICONS: Record<ResourceType, string> = {
  aluminum: 'https://i.ibb.co/Jvc721Q/aluminum.png',
  bauxite: 'https://i.ibb.co/MCX24BV/bauxite.png',
  coal: 'https://i.ibb.co/0Q49PQW/coal.png',
  food: 'https://i.ibb.co/PcbqzMS/steak-meat.png',
  gasoline: 'https://i.ibb.co/WyGLcnL/gasoline.png',
  iron: 'https://i.ibb.co/27cjVPf/iron.png',
  lead: 'https://i.ibb.co/r5KB1rS/lead.png',
  money: 'https://i.ibb.co/cgd2D7s/money.png',
  munitions: 'https://i.ibb.co/LJLjL7g/munitions.png',
  oil: 'https://i.ibb.co/861z21m/oil.png',
  steel: 'https://i.ibb.co/JHVBnW7/steel.png',
  uranium: 'https://i.ibb.co/JB3dhNQ/uranium.png',
  credits: 'https://i.ibb.co/cgd2D7s/money.png', // Fallback
};

interface ResourceIconProps {
  resource: ResourceType;
  value?: number | string;
  showValue?: boolean;
  size?: number;
  suffix?: string;
}

export function ResourceIcon({
  resource,
  value,
  showValue = true,
  size = 20,
  suffix = '',
}: ResourceIconProps) {
  const iconUrl = RESOURCE_ICONS[resource] || RESOURCE_ICONS.money;
  const displayValue = (() => {
    if (typeof value !== 'number') return value;
    if (resource === 'money') return formatMetric(value);
    return formatNumber(value);
  })();

  return (
    <Tooltip label={resource.charAt(0).toUpperCase() + resource.slice(1)}>
      <Group gap={4} wrap="nowrap" style={{ cursor: 'help' }}>
        <Image
          src={iconUrl}
          alt={resource}
          w={size}
          h={size}
          style={{ objectFit: 'contain' }}
        />
        {showValue && value !== undefined && (
          <Text
            size="sm"
            span
            style={{
              fontFamily: 'SF Mono, Monaco, Consolas, monospace',
              fontWeight: 500,
            }}
          >
            {displayValue}
            {suffix}
          </Text>
        )}
      </Group>
    </Tooltip>
  );
}

interface ResourceGridProps {
  resources: Partial<Record<ResourceType, number>>;
  size?: number;
}

/**
 * Display a grid of resource icons with values.
 */
export function ResourceGrid({ resources, size = 18 }: ResourceGridProps) {
  const entries = Object.entries(resources).filter(
    ([, value]) => value !== undefined && value !== 0
  );

  return (
    <Group gap="xs" wrap="wrap">
      {entries.map(([resource, value]) => (
        <ResourceIcon
          key={resource}
          resource={resource as ResourceType}
          value={value}
          size={size}
        />
      ))}
    </Group>
  );
}
