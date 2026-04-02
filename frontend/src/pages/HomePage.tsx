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
  useMantineColorScheme,
} from '@mantine/core';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  IconSword,
  IconBuildingFactory2,
  IconBomb,
  IconBell,
  IconArrowRight,
  IconBrandDiscord,
  IconClock,
} from '@tabler/icons-react';
import { getDiscordLoginUrl } from '@/api/auth';
import { useSidebarDiscordSession } from '@/hooks';
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
            <Image
              src="/splash.webp"
              alt=""
              w={88}
              h={52}
              fit="contain"
              visibleFrom="xs"
              style={{ flexShrink: 0, opacity: isLight ? 0.92 : 0.85 }}
            />
          </Group>
          <Text size="sm" c="dimmed" mt="xs">
            Get DM alerts before nations leave beige or vacation mode.
          </Text>
        </Box>

        <Stack px="lg" py="md" gap="md">
          <Group gap="sm" align="flex-start" wrap="nowrap">
            <ThemeIcon color="indigo" variant="light" size={26} radius="md" style={{ flexShrink: 0 }}>
              <IconClock size={14} />
            </ThemeIcon>
            <Text size="sm" style={{ flex: 1 }}>
              Custom minute offsets before exit
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
          >
            Log in with Discord to unlock
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
        </Stack>

        <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="lg" w="100%">
          {features.map((feature) => {
            if (feature.path === '/reminders' && discordSession.status === 'guest') {
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
