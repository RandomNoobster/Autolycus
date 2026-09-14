import { Container, Stack, Title, Text, List, Code } from '@mantine/core';

export function PrivacyStoragePage() {
  return (
    <Container size="md" py="xl">
      <Stack gap="lg">
        <div>
          <Title order={1}>Privacy & Storage</Title>
          <Text c="dimmed" size="sm" mt={4}>
            Last updated: September 14, 2026
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
            <List.Item>
              Service worker registration (<Code>/sw.js</Code>) - added only when you turn on
              browser notifications on a device. It shows reminder notifications; it does not
              cache pages or see what you browse.
            </List.Item>
            <List.Item>
              Browser push subscription - created by your browser when you turn on
              notifications on a device. It holds the address and encryption keys your
              browser's push service uses to deliver notifications to that device.
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
          <Title order={3}>Notification delivery</Title>
          <Text>
            When you turn on browser notifications on a device, the server stores that
            device's push subscription (endpoint address and encryption keys), a short device
            label such as "Chrome on Windows", and timestamps for when it was added, last seen,
            and last delivered to or failed, linked to your Discord ID. The server removes a
            device when you turn notifications off on it, log out on it, or its push service
            reports that the device is gone.
          </Text>
          <Text>
            Notifications are relayed through your browser vendor's push service (Google,
            Mozilla, Microsoft, or Apple). The notification content is encrypted, so the push
            service can't read it.
          </Text>
          <Text>
            For Discord DMs, the server stores your DM status: the result of the last DM,
            Discord's error code if it failed, and whether you clicked "Got it" in a test DM.
            It also keeps your last 10 delivery problems so the Reminders page can show them.
          </Text>
          <Text>
            Scheduled reminder records are deleted 14 days after they finish, and test DM
            records after 7 days.
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
          <Text>
            To stop browser notifications on a device, open the Reminders page on that device
            and choose "Turn off on this device", or log out there. You can also revoke
            notification permission for this site in your browser's site settings.
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
