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
  Switch,
  Image,
  Button,
  useMantineColorScheme,
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  IconHome,
  IconSword,
  IconBuildingFactory2,
  IconBomb,
  IconBell,
  IconExternalLink,
  IconSun,
  IconMoon,
} from '@tabler/icons-react';
import { useDelayedFlag, useSidebarDiscordSession } from '@/hooks';
import { getLinkedNation } from '@/api/auth';
import { VerifyNationModal } from '@/components/common';
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
    label: 'Reminders',
    path: '/reminders',
    icon: <IconBell size={20} stroke={1.5} />,
    description: 'Manage beige alert timings',
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
  const discordSession = useSidebarDiscordSession();
  const [verifyModalOpen, setVerifyModalOpen] = useState(false);
  const [linkedNationHover, setLinkedNationHover] = useState(false);
  const { data: linkedNationData, isFetched: linkedNationFetched, isLoading: linkedNationLoading } = useQuery({
    queryKey: ['linkedNation'],
    queryFn: async () => {
      try {
        return await getLinkedNation();
      } catch {
        return null;
      }
    },
    retry: false,
  });
  const linkedNationId = linkedNationData?.linked ? linkedNationData.nation_id || '' : '';
  const showLinkedNationLoading = useDelayedFlag(linkedNationLoading, 150);
  const isLightMode = colorScheme === 'light';
  const isDiscordSignedIn = discordSession.status === 'signed_in';

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
          style={{
            filter: isLightMode
              ? 'contrast(1.16) saturate(1.08) drop-shadow(0 1px 2px rgba(124, 45, 18, 0.35))'
              : undefined,
          }}
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

      <Divider my="xs" label="Linked Nation" labelPosition="center" />

      <Stack gap="xs" mih={56} justify="center">
        {!linkedNationFetched ? (
          showLinkedNationLoading ? (
            <Text size="xs" c="dimmed" ta="center">
              Checking linked nation...
            </Text>
          ) : (
            <div style={{ height: 32 }} />
          )
        ) : linkedNationId ? (
          <a
            href={`https://politicsandwar.com/nation/id=${linkedNationId}`}
            target="_blank"
            rel="noopener noreferrer"
            onMouseEnter={() => setLinkedNationHover(true)}
            onMouseLeave={() => setLinkedNationHover(false)}
            style={{
              display: 'block',
              position: 'relative',
              width: '100%',
              overflow: 'hidden',
              borderRadius: 'var(--mantine-radius-sm)',
              border: '1px solid transparent',
              backgroundImage:
                isLightMode
                  ? 'linear-gradient(rgba(255, 255, 255, 0.96), rgba(255, 255, 255, 0.96)), linear-gradient(135deg, rgba(99, 102, 241, 0.35), rgba(249, 115, 22, 0.35))'
                  : 'linear-gradient(var(--mantine-color-dark-7), var(--mantine-color-dark-7)), linear-gradient(135deg, rgba(99, 102, 241, 0.5), rgba(249, 115, 22, 0.5))',
              backgroundOrigin: 'border-box',
              backgroundClip: 'padding-box, border-box',
              padding: '8px 10px',
              boxShadow: isLightMode
                ? '0 2px 8px rgba(15, 23, 42, 0.06)'
                : '0 2px 10px rgba(0, 0, 0, 0.25)',
              textDecoration: 'none',
              color: isLightMode ? 'var(--mantine-color-black)' : 'var(--mantine-color-white)',
              cursor: 'pointer',
              transition: 'box-shadow 120ms ease',
            }}
          >
            <Image
              src={linkedNationData?.flag_url || undefined}
              alt={linkedNationData?.nation_name ? `${linkedNationData.nation_name} flag background` : 'Nation flag background'}
              fallbackSrc="https://politicsandwar.com/img/flags/defaultflag.svg"
              style={{
                position: 'absolute',
                inset: 0,
                zIndex: 0,
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                opacity: isLightMode ? 0.1 : 0.14,
                filter: 'saturate(1.1) blur(1px)',
                pointerEvents: 'none',
              }}
            />
            <div
              aria-hidden
              style={{
                position: 'absolute',
                inset: 0,
                zIndex: 1,
                backgroundColor: linkedNationHover
                  ? isLightMode
                    ? 'rgba(0, 0, 0, 0.04)'
                    : 'rgba(255, 255, 255, 0.06)'
                  : 'transparent',
                transition: 'background-color 120ms ease',
                pointerEvents: 'none',
              }}
            />
            <Group gap={8} wrap="nowrap" justify="center" align="center" style={{ position: 'relative', zIndex: 2 }}>
              <Image
                src={linkedNationData?.flag_url || undefined}
                alt={linkedNationData?.nation_name ? `${linkedNationData.nation_name} flag` : 'Nation flag'}
                w={20}
                h={20}
                radius="sm"
                fallbackSrc="https://politicsandwar.com/img/flags/defaultflag.svg"
                style={{ objectFit: 'cover', flexShrink: 0 }}
              />
              <Text size="sm" fw={600} lh={1.2} ta="center" style={{ color: 'inherit' }}>
                {linkedNationData?.nation_name || 'Linked nation'} (ID: {linkedNationId})
              </Text>
            </Group>
          </a>
        ) : (
          <>
            <Text size="xs" c="dimmed" ta="center">
              {isDiscordSignedIn
                ? 'No nation linked yet.'
                : 'Please log in with Discord before linking your nation.'}
            </Text>
            <Button
              size="xs"
              variant="light"
              onClick={() => setVerifyModalOpen(true)}
              disabled={!isDiscordSignedIn}
            >
              Link Nation
            </Button>
          </>
        )}
      </Stack>
      <VerifyNationModal
        opened={verifyModalOpen}
        onClose={() => setVerifyModalOpen(false)}
      />

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
