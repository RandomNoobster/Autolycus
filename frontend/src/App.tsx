import { Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from '@mantine/core';
import { useDisclosure, useMediaQuery } from '@mantine/hooks';

import { AppNavbar } from '@/components/layout/AppNavbar';
import { AppHeader } from '@/components/layout/AppHeader';
import { AppFooter } from '@/components/layout/AppFooter';
import { RaidsPage } from '@/pages/RaidsPage';
import { BuildsPage } from '@/pages/BuildsPage';
import { DamagePage } from '@/pages/DamagePageView';
import { HomePage } from '@/pages/HomePage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { PrivacyStoragePage } from '@/pages/PrivacyStoragePage';
import { RemindersPage } from '@/pages/RemindersPage';

function App() {
  const [mobileOpened, { toggle: toggleMobile, close: closeMobile }] = useDisclosure();
  // Match Mantine 'sm' breakpoint (48em = 768px). Read synchronously to avoid flash.
  const isMobile = useMediaQuery('(max-width: 48em)', false, {
    getInitialValueInEffect: false,
  });

  return (
    <AppShell
      layout="alt"
      /* Show header only on mobile; sidebar is always visible on desktop */
      {...(isMobile ? { header: { height: 56 } } : {})}
      footer={{ height: 44 }}
      navbar={{
        width: 240,
        breakpoint: 'sm',
        collapsed: { desktop: false, mobile: !mobileOpened },
      }}
      padding={{ base: 'xs', sm: 'md' }}
    >
      {isMobile && (
        <AppShell.Header>
          <AppHeader mobileOpened={mobileOpened} toggleMobile={toggleMobile} />
        </AppShell.Header>
      )}

      <AppShell.Navbar
        p={{ base: 'xs', sm: 'md' }}
        styles={{
          navbar: {
            overflowY: 'auto',
            WebkitOverflowScrolling: 'touch',
            overscrollBehaviorY: 'contain',
          },
        }}
      >
        <AppNavbar onNavigate={closeMobile} isMobileLayout={isMobile} />
      </AppShell.Navbar>

      <AppShell.Main>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/raids" element={<RaidsPage />} />
          <Route path="/reminders" element={<RemindersPage />} />
          <Route path="/builds" element={<BuildsPage />} />
          <Route path="/damage" element={<DamagePage />} />
          <Route path="/privacy" element={<PrivacyStoragePage />} />
          <Route path="/404" element={<NotFoundPage />} />
          <Route path="*" element={<Navigate to="/404" replace />} />
        </Routes>
      </AppShell.Main>
      <AppShell.Footer style={{ borderTop: 'none' }}>
        <AppFooter />
      </AppShell.Footer>
    </AppShell>
  );
}

export default App;
