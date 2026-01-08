/**
 * App Header Component
 *
 * The top navigation bar with branding and global actions.
 */

import { Group, Title, ActionIcon, useMantineColorScheme, Image } from '@mantine/core';
import { IconSun, IconMoon, IconBrandDiscord } from '@tabler/icons-react';

export function AppHeader() {
  const { colorScheme, toggleColorScheme } = useMantineColorScheme();

  return (
    <Group h="100%" px="md" justify="space-between">
      <Group>
        <Image
          src="/assets/icon.png"
          alt="Autolycus"
          w={36}
          h={36}
          fallbackSrc="https://i.ibb.co/2dX2WYW/atomism-ICONSSS.png"
        />
        <Title order={3}>Autolycus</Title>
      </Group>

      <Group>
        <ActionIcon
          variant="subtle"
          size="lg"
          onClick={toggleColorScheme}
          aria-label="Toggle color scheme"
        >
          {colorScheme === 'dark' ? (
            <IconSun size={20} stroke={1.5} />
          ) : (
            <IconMoon size={20} stroke={1.5} />
          )}
        </ActionIcon>

        <ActionIcon
          variant="subtle"
          size="lg"
          component="a"
          href="https://discord.gg/your-server"
          target="_blank"
          aria-label="Join Discord"
        >
          <IconBrandDiscord size={20} stroke={1.5} />
        </ActionIcon>
      </Group>
    </Group>
  );
}
