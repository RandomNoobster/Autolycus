/**
 * App Header Component
 *
 * Mobile-only header with hamburger menu, branding, and theme toggle.
 * Hidden on desktop where the sidebar handles navigation.
 */

import { Group, ActionIcon, useMantineColorScheme, Burger, Image, Box } from '@mantine/core';
import { IconSun, IconMoon } from '@tabler/icons-react';

interface AppHeaderProps {
  mobileOpened: boolean;
  toggleMobile: () => void;
}

export function AppHeader({ mobileOpened, toggleMobile }: AppHeaderProps) {
  const { colorScheme, toggleColorScheme } = useMantineColorScheme();
  const isLightMode = colorScheme === 'light';

  return (
    <Group h="100%" px="xs" justify="space-between" wrap="nowrap">
      <Group gap="xs" wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
        <Burger opened={mobileOpened} onClick={toggleMobile} size="sm" aria-label="Toggle navigation" />
        <Box style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center' }}>
          <Image
            src="/splash.webp"
            alt="Autolycus"
            h={36}
            w="auto"
            maw={180}
            fit="contain"
            fallbackSrc="/splash.webp"
            style={{
              objectPosition: 'left center',
              filter: isLightMode
                ? 'contrast(1.16) saturate(1.08) drop-shadow(0 1px 2px rgba(124, 45, 18, 0.35))'
                : undefined,
            }}
          />
        </Box>
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
