import { Container, Stack, Title, Text, List, Code } from '@mantine/core';

export function PrivacyStoragePage() {
  return (
    <Container size="md" py="xl">
      <Stack gap="lg">
        <div>
          <Title order={1}>Privacy & Storage</Title>
          <Text c="dimmed" size="sm" mt={4}>
            Last updated: November 14, 2026
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
              <Code>autolycus-nuke-targets-filters-v1</Code> - stores your selected nuke
              target filters.
            </List.Item>
            <List.Item>
              <Code>autolycus-builds-disable-pop-income-v1</Code> - remembers the City Builds
              population income setting.
            </List.Item>
            <List.Item>
              <Code>autolycus-table-&lt;tableId&gt;</Code> - stores the table preferences you
              change, such as column visibility, column order, and density (one entry per
              table; the Damage Calculator keeps one per matchup).
            </List.Item>
            <List.Item>
              <Code>mantine-color-scheme-value</Code> - remembers light or dark mode once you
              switch it.
            </List.Item>
            <List.Item>
              <Code>autolycus.discord_session_hint</Code> (session storage, cleared when the tab
              closes) - whether you were signed in, so pages can show the right layout before
              the sign-in check finishes.
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
          <Text size="sm" c="dimmed">
            Older versions also stored <Code>autolycus-access-token-v1-&lt;dataType&gt;</Code>{' '}
            access tokens from Discord bot links. The site no longer reads or writes them;
            clearing this site's data removes any that are left.
          </Text>
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
            When you log in with Discord, Autolycus sets one essential cookie,{' '}
            <Code>session</Code>. It is HttpOnly and SameSite=Lax (and Secure on the live
            site), lasts up to 90 days, and is cleared when you log out. It holds your Discord
            user ID, username, display name and avatar, when you signed in, and the Discord
            access token from that login (the <Code>identify</Code> scope only) with its
            expiry, which lets the server confirm your current Discord username when you
            verify a nation. During login it also briefly holds a random check value and the
            page to return to. The cookie is signed, so it can't be altered, but it is not
            encrypted.
          </Text>
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
