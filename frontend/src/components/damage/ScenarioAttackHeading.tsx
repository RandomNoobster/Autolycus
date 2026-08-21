/**
 * Heading for a damage scenario: attacker → defender with flags and table-matching colors.
 * Nation 1 = blue, Nation 2 = red (same as chart / form).
 */

import { useState } from 'react';
import { Anchor, Box, Center, Group, Image, Stack, Text } from '@mantine/core';
import { IconArrowDown, IconArrowRight, IconShield, IconSword } from '@tabler/icons-react';

import type { NationInfo } from '@/types';

import {
  accentForSlot,
  mantineAnchorColorForSlot,
  nationPanelBackground,
  nationSlotForId,
} from './damageNationTheme';

function BannerNationFlag({ nation }: { nation: NationInfo }) {
  const [failed, setFailed] = useState(false);
  const initial = nation.nationName.trim().charAt(0).toUpperCase() || '?';
  const url = nation.flagUrl?.trim();
  const showImg = Boolean(url) && !failed;

  return (
    <Box
      w={40}
      h={28}
      style={{
        flexShrink: 0,
        borderRadius: 6,
        overflow: 'hidden',
        border: '1px solid rgba(255, 255, 255, 0.22)',
        backgroundColor: 'rgba(0, 0, 0, 0.28)',
      }}
    >
      {showImg ? (
        <Image
          src={url!}
          alt=""
          w={40}
          h={28}
          fit="cover"
          onError={() => setFailed(true)}
        />
      ) : (
        <Center w={40} h={28}>
          <Text fz={13} fw={800} c="dimmed">
            {initial}
          </Text>
        </Center>
      )}
    </Box>
  );
}

interface ScenarioAttackHeadingProps {
  attacker: NationInfo;
  defender: NationInfo;
  nation1Id: number;
}

export function ScenarioAttackHeading({ attacker, defender, nation1Id }: ScenarioAttackHeadingProps) {
  const attackerSlot = nationSlotForId(attacker.id, nation1Id);
  const defenderSlot = nationSlotForId(defender.id, nation1Id);
  const attackerAccent = accentForSlot(attackerSlot);
  const defenderAccent = accentForSlot(defenderSlot);

  const attackerPanel = (
    <Box
      p="sm"
      w="100%"
      style={{
        borderLeft: `4px solid ${attackerAccent}`,
        background: nationPanelBackground(attackerSlot),
        borderRadius: '0 10px 10px 0',
      }}
    >
      <Stack gap={8}>
        <Group gap={6} wrap="nowrap">
          <IconSword size={14} style={{ color: attackerAccent, flexShrink: 0 }} />
          <Text
            size="xs"
            fw={800}
            tt="uppercase"
            style={{ color: attackerAccent, letterSpacing: '0.06em' }}
          >
            Attacking
          </Text>
        </Group>
        <Group gap="sm" wrap="nowrap" align="center">
          <BannerNationFlag nation={attacker} />
          <Anchor
            href={`https://politicsandwar.com/nation/id=${attacker.id}`}
            target="_blank"
            rel="noopener noreferrer"
            fw={700}
            lineClamp={2}
            c={mantineAnchorColorForSlot(attackerSlot)}
            style={{ lineHeight: 1.25 }}
          >
            {attacker.nationName}
          </Anchor>
        </Group>
      </Stack>
    </Box>
  );

  const defenderPanel = (
    <Box
      p="sm"
      w="100%"
      style={{
        borderLeft: `4px solid ${defenderAccent}`,
        background: nationPanelBackground(defenderSlot),
        borderRadius: '0 10px 10px 0',
      }}
    >
      <Stack gap={8}>
        <Group gap={6} wrap="nowrap">
          <IconShield size={14} style={{ color: defenderAccent, flexShrink: 0 }} />
          <Text
            size="xs"
            fw={800}
            tt="uppercase"
            style={{ color: defenderAccent, letterSpacing: '0.06em' }}
          >
            Defending
          </Text>
        </Group>
        <Group gap="sm" wrap="nowrap" align="center">
          <BannerNationFlag nation={defender} />
          <Anchor
            href={`https://politicsandwar.com/nation/id=${defender.id}`}
            target="_blank"
            rel="noopener noreferrer"
            fw={700}
            lineClamp={2}
            c={mantineAnchorColorForSlot(defenderSlot)}
            style={{ lineHeight: 1.25 }}
          >
            {defender.nationName}
          </Anchor>
        </Group>
      </Stack>
    </Box>
  );

  return (
    <Stack gap="sm" mb="lg">
      <Group gap={6} wrap="nowrap">
        <IconSword size={18} style={{ color: attackerAccent, flexShrink: 0 }} />
        <Text size="sm" fw={700} c="dimmed">
          If this attack is performed
        </Text>
      </Group>

      <Stack gap="sm" hiddenFrom="sm">
        {attackerPanel}
        <Center>
          <IconArrowDown
            size={24}
            stroke={1.75}
            style={{ color: attackerAccent, opacity: 0.9 }}
          />
        </Center>
        {defenderPanel}
      </Stack>

      <Group align="stretch" gap="md" wrap="nowrap" visibleFrom="sm">
        <Box style={{ flex: 1, minWidth: 0 }}>{attackerPanel}</Box>
        <Center style={{ flexShrink: 0, alignSelf: 'center' }}>
          <IconArrowRight
            size={26}
            stroke={1.75}
            style={{ color: attackerAccent, opacity: 0.9 }}
          />
        </Center>
        <Box style={{ flex: 1, minWidth: 0 }}>{defenderPanel}</Box>
      </Group>
    </Stack>
  );
}
