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
} from '@mantine/core';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  IconSword,
  IconBuildingFactory2,
  IconBomb,
  IconShield,
  IconArrowRight,
} from '@tabler/icons-react';

const features = [
  {
    icon: IconSword,
    title: 'Raid Targets',
    description:
      'Find profitable targets to raid based on loot value, military strength, and win probability.',
    path: '/raids',
    color: 'red',
  },
  {
    icon: IconBuildingFactory2,
    title: 'City Builds',
    description:
      'Discover optimal city build templates for maximum resource production or income.',
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

  const handleNavigate = (path: string) => {
    // Special handling for raids (requires token)
    if (path === '/raids') {
      const searchParams = new URLSearchParams(location.search);
      const hasToken = searchParams.has('token');
      
      if (hasToken) {
        navigate(`${path}${location.search}`);
      } else {
        navigate(`/token-request?type=raids&redirect=${path}&auto=true`);
      }
    } else {
      // Preserve query params (token) when navigating
      navigate(`${path}${location.search}`);
    }
  };

  return (
    <Container size="lg" py="xl">
      <Stack gap="xl" align="center">
        <Stack gap="sm" align="center" ta="center">
          <ThemeIcon size={80} radius="xl" variant="light">
            <IconShield size={48} />
          </ThemeIcon>
          <Title order={1}>Welcome to Autolycus</Title>
          <Text size="lg" c="dimmed" maw={600}>
            Your comprehensive toolkit for Politics & War. Access raid targets,
            city builds, and damage calculations through Discord links.
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

        <Card shadow="sm" padding="lg" radius="md" withBorder w="100%" maw={600}>
          <Stack gap="md">
            <Title order={4}>How to Use</Title>
            <Text size="sm">
              1. Use the Autolycus Discord bot in your server to generate a
              link.
            </Text>
            <Text size="sm">
              2. Click the link provided by the bot - it will open directly to the
              relevant page.
            </Text>
            <Text size="sm">
              3. Your data is loaded automatically. Use filters, sort columns, and
              explore!
            </Text>
            <Text size="sm" c="dimmed">
              Note: Links expire after 7 days. Request a new link anytime from
              Discord.
            </Text>
          </Stack>
        </Card>
      </Stack>
    </Container>
  );
}
