/**
 * Home Page
 */

import {
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
  IconArrowRight,
} from '@tabler/icons-react';
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
    icon: IconBomb,
    title: 'Damage Calculator',
    description:
      'Analyze war damage potential and plan your attacks for maximum efficiency.',
    path: '/damage',
    color: 'orange',
  },
];

export function HomePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { colorScheme } = useMantineColorScheme();
  const isLightMode = colorScheme === 'light';

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
          {features.map((feature) => (
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
          ))}
        </SimpleGrid>
      </Stack>
    </Container>
  );
}
