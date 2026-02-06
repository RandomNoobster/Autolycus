/**
 * Resource Icon Component
 *
 * Displays game resource icons with optional values.
 */

import { Group, Image, Text, Tooltip } from '@mantine/core';
import type { ResourceType } from '@/types';
import { formatMetric, formatNumber } from '@/utils';

// Resource icon URLs (served from public assets)
const RESOURCE_ICONS: Record<ResourceType, string> = {
  aluminum: '/assets/resources/aluminum.png',
  bauxite: '/assets/resources/bauxite.png',
  coal: '/assets/resources/coal.png',
  food: '/assets/resources/food.png',
  gasoline: '/assets/resources/gasoline.png',
  iron: '/assets/resources/iron.png',
  lead: '/assets/resources/lead.png',
  money: '/assets/resources/money.png',
  munitions: '/assets/resources/munitions.png',
  oil: '/assets/resources/oil.png',
  steel: '/assets/resources/steel.png',
  uranium: '/assets/resources/uranium.png',
  credits: '/assets/resources/credits.png',
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
