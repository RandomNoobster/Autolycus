import { Routes, Route, Navigate, useSearchParams } from 'react-router-dom';
import { AppShell } from '@mantine/core';
import { useDisclosure, useMediaQuery } from '@mantine/hooks';

import { AppNavbar } from '@/components/layout/AppNavbar';
import { AppHeader } from '@/components/layout/AppHeader';
import { RaidsPage } from '@/pages/RaidsPage';
import { BuildsPage } from '@/pages/BuildsPage';
import { DamagePage } from '@/pages/DamagePageView';
import { HomePage } from '@/pages/HomePage';
import { NotFoundPage } from '@/pages/NotFoundPage';

/**
 * Redirect legacy /token-request links to the target page with the auth code.
 * Preserves backward compatibility with existing Discord bot links.
 */
function TokenRedirect() {
  const [searchParams] = useSearchParams();
  const code = searchParams.get('code');
  const redirect = searchParams.get('redirect') || '/raids';
  const target = code
    ? `${redirect}${redirect.includes('?') ? '&' : '?'}code=${encodeURIComponent(code)}`
    : redirect;
  return <Navigate to={target} replace />;
}

function App() {
  const [mobileOpened, { toggle: toggleMobile, close: closeMobile }] = useDisclosure();
  // Match Mantine 'sm' breakpoint (48em = 768px). Read synchronously to avoid flash.
  const isMobile = useMediaQuery('(max-width: 48em)', false, {
    getInitialValueInEffect: false,
  });

  return (
    <AppShell
      /* Show header only on mobile; sidebar is always visible on desktop */
      {...(isMobile ? { header: { height: 56 } } : {})}
      navbar={{
        width: 240,
        breakpoint: 'sm',
        collapsed: { desktop: false, mobile: !mobileOpened },
      }}
      padding="md"
    >
      {isMobile && (
        <AppShell.Header>
          <AppHeader mobileOpened={mobileOpened} toggleMobile={toggleMobile} />
        </AppShell.Header>
      )}

      <AppShell.Navbar p="md">
        <AppNavbar onNavigate={closeMobile} />
      </AppShell.Navbar>

      <AppShell.Main>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/token-request" element={<TokenRedirect />} />
          <Route path="/raids" element={<RaidsPage />} />
          <Route path="/builds" element={<BuildsPage />} />
          <Route path="/damage" element={<DamagePage />} />
          <Route path="/404" element={<NotFoundPage />} />
          <Route path="*" element={<Navigate to="/404" replace />} />
        </Routes>
      </AppShell.Main>
    </AppShell>
  );
}

export default App;
