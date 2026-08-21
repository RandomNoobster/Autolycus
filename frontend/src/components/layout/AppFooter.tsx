import { Anchor, Box, Container, Group, Text } from '@mantine/core';
import { Link, useLocation } from 'react-router-dom';

export function AppFooter() {
  const location = useLocation();
  const year = new Date().getFullYear();

  const links = [
    { to: '/', label: 'Home' },
    { to: '/privacy', label: 'Privacy & Storage' },
  ];

  return (
    <Box h="100%" py={8} px={{ base: 'xs', sm: 'md' }}>
      <Box
        mx={{ base: 'xs', sm: 'md' }}
        mb={8}
        style={{
          borderTop: '1px solid var(--mantine-color-dark-4)',
        }}
      />
      <Container size="xl" h="100%">
        <Group justify="space-between" gap="sm">
          <Text size="xs" c="dimmed">
            © {year} Autolycus
          </Text>
          <Group gap="xs">
            {links.map((item, index) => (
              <Group key={item.to} gap="xs">
                {index > 0 && (
                  <Text size="xs" c="dimmed">
                    •
                  </Text>
                )}
                <Anchor
                  component={Link}
                  to={item.to}
                  size="xs"
                  c={location.pathname === item.to ? 'autolycusOrange.4' : 'dimmed'}
                  td="none"
                  fw={location.pathname === item.to ? 600 : 500}
                >
                  {item.label}
                </Anchor>
              </Group>
            ))}
            <Text size="xs" c="dimmed">
              •
            </Text>
            <Text size="xs" c="dimmed">
              Contact: randomnoobster on Discord
            </Text>
          </Group>
        </Group>
      </Container>
    </Box>
  );
}
