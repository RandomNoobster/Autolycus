import { Container, Stack, Title, Text, List, Code } from '@mantine/core';

export function PrivacyStoragePage() {
  return (
    <Container size="md" py="xl">
      <Stack gap="lg">
        <div>
          <Title order={1}>Privacy & Storage</Title>
          <Text c="dimmed" size="sm" mt={4}>
            Last updated: March 31, 2026
          </Text>
        </div>

        <Text>
          Autolycus uses browser storage to keep core features working and improve your
          experience. At this time, we do not use advertising cookies or third-party
          tracking pixels.
        </Text>

        <Stack gap="xs">
          <Title order={3}>What we store on your device</Title>
          <List spacing="xs">
            <List.Item>
              <Code>autolycus_nation_id</Code> - stores your nation ID so you do not need
              to re-enter it each visit.
            </List.Item>
            <List.Item>
              <Code>autolycus-raids-filters-v1</Code> - stores your selected raid filters
              and view settings.
            </List.Item>
            <List.Item>
              <Code>autolycus-table-&lt;tableId&gt;</Code> - stores table preferences such
              as column visibility, column order, and density.
            </List.Item>
            <List.Item>
              <Code>autolycus-access-token-v1-&lt;dataType&gt;</Code> - stores short-lived
              access tokens used to access protected app data ({' '}
              <Code>raids</Code>, <Code>builds</Code>, <Code>damage</Code> ).
            </List.Item>
          </List>
        </Stack>

        <Stack gap="xs">
          <Title order={3}>Why we use this storage</Title>
          <Text>
            This storage is used for essential app functionality, including remembering
            your preferences, preserving UI state, and keeping authenticated access
            working in the browser.
          </Text>
        </Stack>

        <Stack gap="xs">
          <Title order={3}>Cookies</Title>
          <Text>
            Autolycus does not currently set non-essential analytics or advertising
            cookies. If this changes, we will update this notice and, where required by
            law, request consent before enabling them.
          </Text>
        </Stack>

        <Stack gap="xs">
          <Title order={3}>How to control or delete stored data</Title>
          <Text>
            You can clear your browser data at any time from browser settings, or use
            in-app reset and clear actions where available. Clearing storage may sign you
            out of certain views and reset saved preferences.
          </Text>
        </Stack>

        <Stack gap="xs">
          <Title order={3}>Contact</Title>
          <Text>
            If you have privacy questions, please contact the Autolycus maintainers.
          </Text>
        </Stack>
      </Stack>
    </Container>
  );
}
