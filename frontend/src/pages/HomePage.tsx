/**
 * Home Page
 */

import {
  Box,
  Button,
  Container,
  Title,
  Text,
  Stack,
  Card,
  SimpleGrid,
  Group,
  ThemeIcon,
  Image,
  Skeleton,
  useMantineColorScheme,
} from '@mantine/core';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  IconSword,
  IconBuildingFactory2,
  IconBomb,
  IconBell,
  IconRadioactive,
  IconArrowRight,
  IconBrandDiscord,
  IconStar,
} from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { fetchPublicStats } from '@/api';
import { getDiscordLoginUrl } from '@/api/auth';
import { readDiscordSessionHint, useSidebarDiscordSession } from '@/hooks';
import { internalNavPath } from '@/lib/internalNavPath';

const features = [
  {
    icon: IconSword,
    title: 'Raid Targets',
    description:
      'Find profitable targets to raid based on loot value, military strength, and more.',
    path: '/raids',
    color: 'red',
  },
  {
    icon: IconRadioactive,
    title: 'Nuke Targets',
    description:
      'Rank nations by attrition nuke and missile damage, including simulated war net damage.',
    path: '/nuke-targets',
    color: 'pink',
  },
  {
    icon: IconBuildingFactory2,
    title: 'City Builds',
    description:
      'Discover optimal city build templates for maximum income.',
    path: '/builds',
    color: 'blue',
  },
  {
    icon: IconBell,
    title: 'Reminders',
    description:
      'Manage active beige reminders, delete old ones, and set minute offsets for alert timing.',
    path: '/reminders',
    color: 'grape',
  },
  {
    icon: IconBomb,
    title: 'Damage Calculator',
    description:
      'Analyze war damage potential and plan your attacks for maximum efficiency.',
    path: '/damage',
    color: 'orange',
  },
];

/** Social proof from GET /api/stats/public (Mongo ``global_users`` count). */
function HomeRegisteredUsersBlurb({
  count,
  isLoading,
}: {
  count: number | null;
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <Text size="sm" maw={520} style={{ minHeight: '1.55em' }}>
        <Text span c="dimmed">
          Join{' '}
        </Text>
        <Skeleton
          height={18}
          width={44}
          radius="sm"
          component="span"
          style={{ verticalAlign: 'middle', display: 'inline-block' }}
        />
        <Text span c="dimmed">
          {' '}
          other registered users already using Autolycus with Discord.
        </Text>
      </Text>
    );
  }

  if (count === null || count <= 0) {
    return (
      <Text size="sm" c="dimmed" maw={520} style={{ minHeight: '1.55em' }}>
        Be among the first registered users—link your nation with Discord.
      </Text>
    );
  }

  const formatted = count.toLocaleString();
  const rest =
    count === 1
      ? ' other registered user already using Autolycus with Discord.'
      : ' other registered users already using Autolycus with Discord.';
  return (
    <Text size="sm" maw={520} style={{ minHeight: '1.55em' }}>
      <Text span c="dimmed">
        Join{' '}
      </Text>
      <Text span fw={700}>
        {formatted}
      </Text>
      <Text span c="dimmed">
        {rest}
      </Text>
    </Text>
  );
}

function HomeRemindersGuestCard() {
  const { colorScheme } = useMantineColorScheme();
  const isLight = colorScheme === 'light';
  const loginUrl = getDiscordLoginUrl('/reminders');

  return (
    <Card
      padding={0}
      radius="md"
      withBorder
      style={{
        overflow: 'hidden',
        borderColor: isLight ? 'var(--mantine-color-indigo-2)' : 'var(--mantine-color-dark-4)',
        background: isLight
          ? 'linear-gradient(145deg, rgba(99, 102, 241, 0.06) 0%, rgba(249, 115, 22, 0.08) 50%, rgba(255, 255, 255, 0.95) 100%)'
          : 'linear-gradient(145deg, rgba(88, 101, 242, 0.12) 0%, rgba(249, 115, 22, 0.1) 45%, var(--mantine-color-dark-7) 100%)',
        boxShadow: isLight
          ? '0 12px 32px rgba(15, 23, 42, 0.08)'
          : '0 16px 40px rgba(0, 0, 0, 0.45)',
      }}
    >
      <Stack gap={0}>
        <Box
          px="lg"
          pt="lg"
          pb="sm"
          style={{
            borderBottom: `1px solid ${isLight ? 'var(--mantine-color-gray-2)' : 'var(--mantine-color-dark-5)'}`,
          }}
        >
          <Group justify="space-between" align="flex-start" wrap="nowrap" gap="sm">
            <Group gap="sm" wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
              <ThemeIcon
                size={44}
                radius="md"
                variant="gradient"
                gradient={{ from: 'indigo', to: 'orange', deg: 125 }}
                style={{ flexShrink: 0 }}
              >
                <IconBell size={24} stroke={1.5} />
              </ThemeIcon>
              <div style={{ minWidth: 0 }}>
                <Text size="xs" tt="uppercase" fw={700} c="dimmed" lts={1.2}>
                  Discord perk
                </Text>
                <Title order={4} style={{ lineHeight: 1.25 }}>
                  Reminders
                </Title>
              </div>
            </Group>
          </Group>
          <Text size="sm" c="dimmed" mt="xs">
            Get DM alerts before nations leave beige or vacation mode.
          </Text>
        </Box>

        <Stack px="lg" py="md" gap="md">
          <Group gap="sm" align="flex-start" wrap="nowrap">
            <ThemeIcon color="indigo" variant="light" size={26} radius="md" style={{ flexShrink: 0 }}>
              <IconStar size={14} />
            </ThemeIcon>
            <Text size="sm" style={{ flex: 1 }}>
              Customize when they get sent and how many reminders you get
            </Text>
          </Group>

          <Button
            component="a"
            href={loginUrl}
            size="lg"
            fullWidth
            color="indigo"
            variant="filled"
            leftSection={<IconBrandDiscord size={22} />}
            styles={{
              root: { minWidth: 0 },
              inner: { flexWrap: 'wrap', justifyContent: 'center', rowGap: 4 },
              label: { whiteSpace: 'normal', textAlign: 'center', lineHeight: 1.25 },
            }}
          >
            Log in with Discord
          </Button>
        </Stack>
      </Stack>
    </Card>
  );
}

export function HomePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { colorScheme } = useMantineColorScheme();
  const isLightMode = colorScheme === 'light';
  const discordSession = useSidebarDiscordSession();
  const showRemindersGuestPromo =
    discordSession.status === 'guest' ||
    (discordSession.status === 'loading' && readDiscordSessionHint() !== 'signed_in');

  const publicStatsQuery = useQuery({
    queryKey: ['home', 'public-stats'],
    queryFn: fetchPublicStats,
    staleTime: 300_000,
    gcTime: 600_000,
  });
  const registeredUsers = publicStatsQuery.data?.registered_users ?? null;
  const isLoadingPublicStats = publicStatsQuery.isLoading;

  const handleNavigate = (path: string) => {
    navigate(internalNavPath(path, location.search));
  };

  return (
    <Container size="lg" py="xl">
      <Stack gap="xl" align="center">
        <Stack gap="sm" align="center" ta="center">
          <Text
            size="xl"
            fw={700}
            style={{
              fontFamily: "'Trebuchet MS', 'Segoe UI', 'Arial', sans-serif",
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: isLightMode ? '#b45309' : '#ffd38a',
              textShadow:
                isLightMode
                  ? '0 1px 0 rgba(255, 255, 255, 0.8), 0 2px 6px rgba(120, 53, 15, 0.2)'
                  : '0 0 6px rgba(255, 171, 64, 0.45), 0 0 14px rgba(255, 109, 0, 0.35), 0 2px 10px rgba(120, 28, 0, 0.65)',
            }}
          >
            Welcome to
          </Text>
          <Image
            src="/splash.webp"
            alt="Autolycus"
            maw={620}
            w="100%"
          />
          <Text size="lg" c="dimmed" maw={600}>
            Your comprehensive toolkit for Politics & War. Access raid targets,
            city builds, and damage calculations.
          </Text>
          <HomeRegisteredUsersBlurb
            count={registeredUsers}
            isLoading={isLoadingPublicStats}
          />
        </Stack>

        <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="lg" w="100%">
          {features.map((feature) => {
            if (feature.path === '/reminders' && showRemindersGuestPromo) {
              return <HomeRemindersGuestCard key={feature.path} />;
            }

            return (
              <Card
                key={feature.path}
                shadow="sm"
                padding="lg"
                radius="md"
                withBorder
                style={{ cursor: 'pointer' }}
                onClick={() => handleNavigate(feature.path)}
              >
                <Stack gap="md">
                  <ThemeIcon size={48} radius="md" variant="light" color={feature.color}>
                    <feature.icon size={28} />
                  </ThemeIcon>
                  <Stack gap="xs">
                    <Title order={3}>{feature.title}</Title>
                    <Text size="sm" c="dimmed">
                      {feature.description}
                    </Text>
                  </Stack>
                  <Group gap="xs" c={feature.color}>
                    <Text size="sm" fw={500}>
                      Go to {feature.title}
                    </Text>
                    <IconArrowRight size={16} />
                  </Group>
                </Stack>
              </Card>
            );
          })}
        </SimpleGrid>
      </Stack>
    </Container>
  );
}
