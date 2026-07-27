/**
 * App Navbar Component
 *
 * Sidebar navigation. Always visible on desktop, toggled via hamburger on mobile.
 * Desktop: flex column — nav scrolls if needed; account + theme stay pinned at bottom.
 */

import {
  Box,
  Button,
  Divider,
  Flex,
  Group,
  Image,
  Modal,
  NavLink,
  ScrollArea,
  Stack,
  Switch,
  Text,
  Tooltip,
  Badge,
  useMantineColorScheme,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  IconHome,
  IconSword,
  IconBuildingFactory2,
  IconBomb,
  IconBell,
  IconRadioactive,
  IconExternalLink,
  IconSun,
  IconMoon,
  IconUnlink,
  IconReplace,
} from '@tabler/icons-react';
import { useDelayedFlag, useSidebarDiscordSession } from '@/hooks';
import { getLinkedNation, unlinkDiscordNation } from '@/api/auth';
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
    label: 'Nuke Targets',
    path: '/nuke-targets',
    icon: <IconRadioactive size={20} stroke={1.5} />,
    description: 'Nuke & missile damage',
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
  /** Below `sm` breakpoint: full-height flex + spacer are disabled so the drawer can scroll. */
  isMobileLayout?: boolean;
}

const navLinkRootStyle = {
  borderRadius: 'var(--mantine-radius-md)',
  textDecoration: 'none' as const,
  paddingTop: 6,
  paddingBottom: 6,
  width: '100%',
};

function SectionDivider({ label }: { label?: string }) {
  return (
    <Divider
      my={4}
      label={label}
      labelPosition="center"
      styles={{ label: { fontSize: 'var(--mantine-font-size-xs)' } }}
    />
  );
}

export function AppNavbar({ onNavigate, isMobileLayout = false }: AppNavbarProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const { colorScheme, toggleColorScheme } = useMantineColorScheme();
  const discordSession = useSidebarDiscordSession();
  const [verifyModalOpen, setVerifyModalOpen] = useState(false);
  const [unlinkConfirmOpen, setUnlinkConfirmOpen] = useState(false);
  const [linkedNationHover, setLinkedNationHover] = useState(false);
  const [unlinkingNation, setUnlinkingNation] = useState(false);

  const isCompactHeight = useMediaQuery('(max-height: 880px)', false, {
    getInitialValueInEffect: false,
  });
  const isTightHeight = useMediaQuery('(max-height: 740px)', false, {
    getInitialValueInEffect: false,
  });

  const showNavDescriptions = !isCompactHeight;
  const logoMaxWidth = isTightHeight ? 108 : isCompactHeight ? 132 : 160;

  const {
    data: linkedNationData,
    isFetched: linkedNationFetched,
    isLoading: linkedNationLoading,
    refetch: refetchLinkedNation,
  } = useQuery({
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
    event.preventDefault();
    navigate(internalNavPath(item.path, location.search));
    onNavigate?.();
  };

  const navLinkLightStyles = isLightMode
    ? {
        section: { color: 'var(--mantine-color-gray-7)' },
        label: { color: 'var(--mantine-color-black)', fontWeight: 600, textDecoration: 'none' },
        description: { color: 'var(--mantine-color-gray-7)', textDecoration: 'none' },
      }
    : undefined;

  const mainNav = (
    <Stack gap={2}>
      {navItems.map((item) => {
        const link = (
          <NavLink
            key={item.path}
            label={
              <Group gap="xs" wrap="nowrap">
                <Text size="sm" lh={1.2}>
                  {item.label}
                </Text>
                {item.badge ? (
                  <Badge size="xs" variant="light" color="green">
                    {item.badge}
                  </Badge>
                ) : null}
              </Group>
            }
            description={showNavDescriptions ? item.description : undefined}
            leftSection={item.icon}
            active={location.pathname === item.path}
            onClick={(e) => handleInternalNav(e, item)}
            variant="light"
            style={{
              ...navLinkRootStyle,
              backgroundColor:
                isLightMode && location.pathname === item.path
                  ? 'var(--mantine-color-orange-0)'
                  : undefined,
              border:
                isLightMode && location.pathname === item.path
                  ? '1px solid var(--mantine-color-orange-2)'
                  : undefined,
            }}
            styles={navLinkLightStyles}
          />
        );

        if (!showNavDescriptions && item.description) {
          return (
            <Tooltip key={item.path} label={item.description} position="right" withArrow>
              <Box w="100%">{link}</Box>
            </Tooltip>
          );
        }
        return link;
      })}
    </Stack>
  );

  const externalNav = (
    <Stack gap={2}>
      {externalLinks.map((item) => (
        <NavLink
          key={item.path}
          label={<Text size="sm" lh={1.2}>{item.label}</Text>}
          leftSection={item.icon}
          onClick={() => handleExternalNav(item)}
          variant="subtle"
          style={navLinkRootStyle}
          styles={
            isLightMode
              ? {
                  section: { color: 'var(--mantine-color-gray-7)' },
                  label: { color: 'var(--mantine-color-black)', fontWeight: 500, textDecoration: 'none' },
                }
              : undefined
          }
        />
      ))}
    </Stack>
  );

  const accountFooter = (
    <Stack gap={6} style={{ flexShrink: 0 }}>
      <SectionDivider label="Discord" />
      <DiscordSidebarCard session={discordSession} compact={isCompactHeight} />

      <SectionDivider label="Linked Nation" />

      <Stack gap={6} justify="center">
        {!linkedNationFetched ? (
          showLinkedNationLoading ? (
            <Text size="xs" c="dimmed" ta="center">
              Checking linked nation...
            </Text>
          ) : (
            <div style={{ height: 24 }} />
          )
        ) : linkedNationId ? (
          <>
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
                backgroundImage: isLightMode
                  ? 'linear-gradient(rgba(255, 255, 255, 0.96), rgba(255, 255, 255, 0.96)), linear-gradient(135deg, rgba(99, 102, 241, 0.35), rgba(249, 115, 22, 0.35))'
                  : 'linear-gradient(var(--mantine-color-dark-7), var(--mantine-color-dark-7)), linear-gradient(135deg, rgba(99, 102, 241, 0.5), rgba(249, 115, 22, 0.5))',
                backgroundOrigin: 'border-box',
                backgroundClip: 'padding-box, border-box',
                padding: isCompactHeight ? '6px 8px' : '8px 10px',
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
                alt={
                  linkedNationData?.nation_name
                    ? `${linkedNationData.nation_name} flag background`
                    : 'Nation flag background'
                }
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
              <Group
                gap={6}
                wrap="nowrap"
                justify="center"
                align="center"
                style={{ position: 'relative', zIndex: 2 }}
              >
                <Image
                  src={linkedNationData?.flag_url || undefined}
                  alt={
                    linkedNationData?.nation_name
                      ? `${linkedNationData.nation_name} flag`
                      : 'Nation flag'
                  }
                  w={18}
                  h={18}
                  radius="sm"
                  fallbackSrc="https://politicsandwar.com/img/flags/defaultflag.svg"
                  style={{ objectFit: 'cover', flexShrink: 0 }}
                />
                <Text
                  size={isCompactHeight ? 'xs' : 'sm'}
                  fw={600}
                  lh={1.2}
                  ta="center"
                  lineClamp={2}
                  style={{ color: 'inherit' }}
                >
                  {linkedNationData?.nation_name || 'Linked nation'} (ID: {linkedNationId})
                </Text>
              </Group>
            </a>
            <Group gap={4} wrap="wrap">
              <Button
                size="compact-xs"
                variant="subtle"
                color="gray"
                leftSection={<IconUnlink size={12} />}
                onClick={() => setUnlinkConfirmOpen(true)}
              >
                Remove Link
              </Button>
              <Button
                size="compact-xs"
                variant="subtle"
                color="gray"
                leftSection={<IconReplace size={12} />}
                onClick={() => setVerifyModalOpen(true)}
              >
                Change Nation
              </Button>
            </Group>
          </>
        ) : (
          <>
            <Text size="xs" c="dimmed" ta="center" lh={1.3}>
              {isDiscordSignedIn
                ? 'No nation linked yet.'
                : 'Log in with Discord before linking your nation.'}
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

      <SectionDivider />

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

  const branding = (
    <Box style={{ flexShrink: 0 }}>
      <Group gap="xs" py={isCompactHeight ? 2 : 4} justify="center">
        <Image
          src="/splash.webp"
          alt="Autolycus"
          maw={logoMaxWidth}
          w="100%"
          fallbackSrc="/splash.webp"
          style={{
            filter: isLightMode
              ? 'contrast(1.16) saturate(1.08) drop-shadow(0 1px 2px rgba(124, 45, 18, 0.35))'
              : undefined,
          }}
        />
      </Group>
      <SectionDivider />
    </Box>
  );

  const scrollableNav = (
    <Stack gap={6}>
      {mainNav}
      <SectionDivider label="External" />
      {externalNav}
    </Stack>
  );

  const modals = (
    <>
      <Modal
        opened={unlinkConfirmOpen}
        onClose={() => {
          if (!unlinkingNation) setUnlinkConfirmOpen(false);
        }}
        title="Remove nation link"
        centered
      >
        <Stack gap="md">
          <Text size="sm" c="dimmed">
            Remove the link between your Discord account and this nation? You can link again later
            with Verify Nation.
          </Text>
          <Group justify="flex-end" gap="xs">
            <Button
              variant="default"
              disabled={unlinkingNation}
              onClick={() => setUnlinkConfirmOpen(false)}
            >
              Cancel
            </Button>
            <Button
              color="red"
              loading={unlinkingNation}
              onClick={async () => {
                if (unlinkingNation) return;
                setUnlinkingNation(true);
                try {
                  await unlinkDiscordNation();
                  await refetchLinkedNation();
                  setUnlinkConfirmOpen(false);
                } finally {
                  setUnlinkingNation(false);
                }
              }}
            >
              Remove link
            </Button>
          </Group>
        </Stack>
      </Modal>

      <VerifyNationModal
        opened={verifyModalOpen}
        onClose={() => setVerifyModalOpen(false)}
        onVerified={() => {
          void refetchLinkedNation();
        }}
      />
    </>
  );

  if (isMobileLayout) {
    return (
      <Stack gap={6}>
        {branding}
        {scrollableNav}
        {accountFooter}
        {modals}
      </Stack>
    );
  }

  return (
    <Flex direction="column" h="100%" mah="100%" gap={0} style={{ minHeight: 0 }}>
      {branding}
      <ScrollArea
        style={{ flex: 1, minHeight: 0 }}
        type="hover"
        scrollbarSize={6}
      >
        {scrollableNav}
      </ScrollArea>
      <Box pt={6} style={{ flexShrink: 0 }}>
        {accountFooter}
      </Box>
      {modals}
    </Flex>
  );
}
