/**
 * App Navbar Component
 *
 * Sidebar navigation. Always visible on desktop, toggled via hamburger on mobile.
 * Includes branding, nav links, external links, nation ID field, theme toggle,
 * and footer text.
 */

import {
  NavLink,
  Stack,
  Text,
  Divider,
  Badge,
  Group,
  ActionIcon,
  Switch,
  Image,
  useMantineColorScheme,
} from '@mantine/core';
import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  IconHome,
  IconSword,
  IconBuildingFactory2,
  IconBomb,
  IconExternalLink,
  IconCheck,
  IconX,
  IconSun,
  IconMoon,
} from '@tabler/icons-react';
import { useNationId, useSidebarDiscordSession } from '@/hooks';
import { NationIdField } from '@/components/common';
import { DiscordSidebarCard } from '@/components/layout/DiscordSidebarCard';
import { internalNavPath } from '@/lib/internalNavPath';

interface NavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
  description?: string;
  external?: boolean;
  badge?: string;
}

const navItems: NavItem[] = [
  {
    label: 'Home',
    path: '/',
    icon: <IconHome size={20} stroke={1.5} />,
    description: 'Welcome page',
  },
  {
    label: 'Raid Targets',
    path: '/raids',
    icon: <IconSword size={20} stroke={1.5} />,
    description: 'Find profitable targets',
  },
  {
    label: 'City Builds',
    path: '/builds',
    icon: <IconBuildingFactory2 size={20} stroke={1.5} />,
    description: 'Optimal city templates',
  },
  {
    label: 'Damage Calculator',
    path: '/damage',
    icon: <IconBomb size={20} stroke={1.5} />,
    description: 'War damage analysis',
  },
];

const externalLinks: NavItem[] = [
  {
    label: 'Politics & War',
    path: 'https://politicsandwar.com',
    icon: <IconExternalLink size={16} stroke={1.5} />,
    external: true,
  },
  {
    label: 'Import Template',
    path: 'https://politicsandwar.com/city/improvements/bulk-import/',
    icon: <IconExternalLink size={16} stroke={1.5} />,
    external: true,
  },
];

interface AppNavbarProps {
  /** Called after a navigation event so the parent can close the mobile drawer. */
  onNavigate?: () => void;
}

export function AppNavbar({ onNavigate }: AppNavbarProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const { colorScheme, toggleColorScheme } = useMantineColorScheme();
  const { nationId, setNationId, clearNationId, parseNationId } = useNationId();
  const discordSession = useSidebarDiscordSession();
  const [inputValue, setInputValue] = useState(nationId);
  const [error, setError] = useState('');
  const isLightMode = colorScheme === 'light';

  const handleSaveNationId = () => {
    const parsed = parseNationId(inputValue);
    if (parsed) {
      setNationId(parsed);
      setInputValue(parsed);
      setError('');
    } else {
      setError('Invalid nation ID or link');
    }
  };

  const handleClearNationId = () => {
    clearNationId();
    setInputValue('');
    setError('');
  };

  const handleExternalNav = (item: NavItem) => {
    window.open(item.path, '_blank', 'noopener,noreferrer');
    onNavigate?.();
  };

  const handleInternalNav = (event: React.MouseEvent, item: NavItem) => {
    // Mantine NavLink renders an <a> without href; prevent the browser from
    // handling the click so client-side routing is reliable.
    event.preventDefault();
    navigate(internalNavPath(item.path, location.search));
    onNavigate?.();
  };

  return (
    <Stack gap="xs" h="100%">
      {/* Branding — visible in sidebar (desktop) */}
      <Group gap="xs" py={4} justify="center">
        <Image
          src="/splash.webp"
          alt="Autolycus"
          maw={180}
          w="100%"
          fallbackSrc="/splash.webp"
        />
      </Group>

      <Divider />

      {/* Main nav */}
      <Stack gap={4}>
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            label={
              <Group gap="xs">
                <Text size="sm">{item.label}</Text>
                {item.badge && (
                  <Badge size="xs" variant="light" color="green">
                    {item.badge}
                  </Badge>
                )}
              </Group>
            }
            description={item.description}
            leftSection={item.icon}
            active={location.pathname === item.path}
            onClick={(e) => handleInternalNav(e, item)}
            variant="light"
            style={{
              borderRadius: 'var(--mantine-radius-md)',
              textDecoration: 'none',
              backgroundColor:
                isLightMode && location.pathname === item.path
                  ? 'var(--mantine-color-orange-0)'
                  : undefined,
              border:
                isLightMode && location.pathname === item.path
                  ? '1px solid var(--mantine-color-orange-2)'
                  : undefined,
            }}
            styles={
              isLightMode
                ? {
                    section: {
                      color: 'var(--mantine-color-gray-7)',
                    },
                    label: {
                      color: 'var(--mantine-color-black)',
                      fontWeight: 600,
                      textDecoration: 'none',
                    },
                    description: {
                      color: 'var(--mantine-color-gray-7)',
                      textDecoration: 'none',
                    },
                  }
                : undefined
            }
          />
        ))}
      </Stack>

      <Divider my="xs" label="External" labelPosition="center" />

      <Stack gap={4}>
        {externalLinks.map((item) => (
          <NavLink
            key={item.path}
            label={item.label}
            leftSection={item.icon}
            onClick={() => handleExternalNav(item)}
            variant="subtle"
            style={{ borderRadius: 'var(--mantine-radius-md)', textDecoration: 'none' }}
            styles={
              isLightMode
                ? {
                    section: {
                      color: 'var(--mantine-color-gray-7)',
                    },
                    label: {
                      color: 'var(--mantine-color-black)',
                      fontWeight: 500,
                      textDecoration: 'none',
                    },
                  }
                : undefined
            }
          />
        ))}
      </Stack>

      {/* Spacer */}
      <div style={{ flexGrow: 1 }} />

      <Divider my="xs" label="Discord" labelPosition="center" />

      <DiscordSidebarCard session={discordSession} />

      <Divider my="xs" label="Your Nation" labelPosition="center" />

      <Stack gap="xs">
        <NationIdField
          placeholder="Nation ID or Link"
          size="xs"
          value={inputValue || ''}
          onChange={(value) => {
            setInputValue(value);
            setError('');
          }}
          onSubmit={handleSaveNationId}
          buttonLabel="Save"
          buttonIcon={<IconCheck size={14} />}
          buttonDisabled={!inputValue || inputValue === nationId}
          layout="column"
          inputProps={{
            error,
            rightSection:
              inputValue && (
                <ActionIcon
                  size="xs"
                  variant="subtle"
                  color="gray"
                  onClick={handleClearNationId}
                >
                  <IconX size={14} />
                </ActionIcon>
              ),
          }}
          buttonProps={{ fullWidth: true }}
        />
        {nationId && (
          <Text size="xs" c="dimmed" ta="center">
            Current: {nationId}
          </Text>
        )}
      </Stack>

      <Divider my="xs" />

      {/* Footer: theme toggle */}
      <Switch
        checked={colorScheme === 'dark'}
        onChange={toggleColorScheme}
        label={colorScheme === 'dark' ? 'Dark mode' : 'Light mode'}
        size="sm"
        onLabel={<IconMoon size={14} stroke={1.5} />}
        offLabel={<IconSun size={14} stroke={1.5} />}
      />
    </Stack>
  );
}
