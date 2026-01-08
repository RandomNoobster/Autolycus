/**
 * App Navbar Component
 *
 * The side navigation with links to different pages.
 */

import { NavLink, Stack, Text, Divider, Badge, Group } from '@mantine/core';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  IconHome,
  IconSword,
  IconBuildingFactory2,
  IconBomb,
  IconExternalLink,
} from '@tabler/icons-react';

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
    badge: 'Secure',
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
    label: 'City Import',
    path: 'https://politicsandwar.com/city/improvements/bulk-import/',
    icon: <IconExternalLink size={16} stroke={1.5} />,
    external: true,
  },
];

export function AppNavbar() {
  const location = useLocation();
  const navigate = useNavigate();

  const handleNavClick = (item: NavItem) => {
    if (item.external) {
      window.open(item.path, '_blank');
    } else if (item.path === '/raids') {
      // For raids, check if we have a token
      const searchParams = new URLSearchParams(location.search);
      const hasToken = searchParams.has('token');
      
      if (hasToken) {
        // Navigate with existing token
        navigate(`${item.path}${location.search}`);
      } else {
        // Redirect to token request page with auto-generate
        navigate(`/token-request?type=raids&redirect=${item.path}&auto=true`);
      }
    } else {
      // Preserve query params when navigating (for tokens)
      const searchParams = location.search;
      navigate(`${item.path}${searchParams}`);
    }
  };

  return (
    <Stack gap="xs" h="100%">
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
            onClick={() => handleNavClick(item)}
            variant="light"
            style={{ borderRadius: 'var(--mantine-radius-md)' }}
          />
        ))}
      </Stack>

      <Divider my="sm" label="External Links" labelPosition="center" />

      <Stack gap={4}>
        {externalLinks.map((item) => (
          <NavLink
            key={item.path}
            label={item.label}
            leftSection={item.icon}
            onClick={() => handleNavClick(item)}
            variant="subtle"
            style={{ borderRadius: 'var(--mantine-radius-md)' }}
          />
        ))}
      </Stack>

      <div style={{ flexGrow: 1 }} />

      <Text size="xs" c="dimmed" ta="center">
        Please report bugs to RandomNoobster
        <br />
        Courtesy of Church of Atom
      </Text>
    </Stack>
  );
}
