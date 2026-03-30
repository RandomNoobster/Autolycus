/**
 * App Header Component
 *
 * Mobile-only header with hamburger menu, branding, and theme toggle.
 * Hidden on desktop where the sidebar handles navigation.
 */

import { Group, Title, ActionIcon, useMantineColorScheme, Burger, Image } from '@mantine/core';
import { IconSun, IconMoon } from '@tabler/icons-react';

interface AppHeaderProps {
  mobileOpened: boolean;
  toggleMobile: () => void;
}

export function AppHeader({ mobileOpened, toggleMobile }: AppHeaderProps) {
  const { colorScheme, toggleColorScheme } = useMantineColorScheme();

  return (
    <Group h="100%" px="md" justify="space-between">
      <Group gap="xs">
        <Burger opened={mobileOpened} onClick={toggleMobile} size="sm" aria-label="Toggle navigation" />
        <Image
          src="/assets/icon.png"
          alt="Autolycus"
          w={28}
          h={28}
          fallbackSrc="/assets/icon.png"
        />
        <Title order={4}>Autolycus</Title>
      </Group>

      <ActionIcon
        variant="subtle"
        size="lg"
        onClick={toggleColorScheme}
        aria-label="Toggle color scheme"
      >
        {colorScheme === 'dark' ? (
          <IconSun size={18} stroke={1.5} />
        ) : (
          <IconMoon size={18} stroke={1.5} />
        )}
      </ActionIcon>
    </Group>
  );
}
