import { lazy, Suspense, useEffect, useRef } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AppShell } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';

import { AppNavbar } from '@/components/layout/AppNavbar';
import { AppHeader } from '@/components/layout/AppHeader';
import { AppFooter } from '@/components/layout/AppFooter';
import { MobileNavOpenContext } from '@/components/layout/MobileNavOpenContext';
import { LoadingState } from '@/components/common/LoadingState';
import { useIsMobile } from '@/hooks/useIsMobile';
import { HomePage } from '@/pages/HomePage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { PrivacyStoragePage } from '@/pages/PrivacyStoragePage';

// The tool pages carry the table and chart libraries; load each when its route is opened.
const RaidsPage = lazy(() => import('@/pages/RaidsPage').then((m) => ({ default: m.RaidsPage })));
const NukeTargetsPage = lazy(() =>
  import('@/pages/NukeTargetsPage').then((m) => ({ default: m.NukeTargetsPage }))
);
const RemindersPage = lazy(() =>
  import('@/pages/RemindersPage').then((m) => ({ default: m.RemindersPage }))
);
const BuildsPage = lazy(() => import('@/pages/BuildsPage').then((m) => ({ default: m.BuildsPage })));
const DamagePage = lazy(() =>
  import('@/pages/DamagePageView').then((m) => ({ default: m.DamagePage }))
);

const ROUTE_TITLES: Record<string, string> = {
  '/raids': 'Raid Targets',
  '/nuke-targets': 'Nuke Targets',
  '/reminders': 'Reminders',
  '/builds': 'City Builds',
  '/damage': 'Damage Calculator',
  '/privacy': 'Privacy & Storage',
  '/404': 'Page Not Found',
};

/** The site origin from the build-time canonical link, or this page's origin if it has none. */
function canonicalOrigin(link: HTMLLinkElement): string {
  try {
    const url = new URL(link.getAttribute('href') ?? '', window.location.href);
    if (url.protocol === 'http:' || url.protocol === 'https:') return url.origin;
  } catch {
    // e.g. "//" when VITE_SITE_ORIGIN is unset in dev
  }
  return window.location.origin;
}

/** index.html has one static title and canonical link; keep both per route. */
function useRouteHead(pathname: string) {
  useEffect(() => {
    const name = ROUTE_TITLES[pathname];
    document.title = name ? `${name} · Autolycus` : 'Autolycus';
    const canonical = document.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (canonical) canonical.href = `${canonicalOrigin(canonical)}${pathname}`;
  }, [pathname]);
}

function App() {
  const [mobileOpened, { toggle: toggleMobile, close: closeMobile }] = useDisclosure();
  const isMobile = useIsMobile();
  const location = useLocation();
  const navbarRef = useRef<HTMLElement>(null);
  useRouteHead(location.pathname);

  // A closed mobile drawer is only moved off-screen; keep its controls out of reach
  // of Tab and screen readers until it opens.
  const navbarHidden = isMobile && !mobileOpened;
  useEffect(() => {
    if (navbarRef.current) navbarRef.current.inert = navbarHidden;
  }, [navbarHidden]);

  // Leaving the mobile layout with the drawer open would keep AppShell's full-width
  // "open" rule, which still matches at exactly 768px.
  useEffect(() => {
    if (!isMobile) closeMobile();
  }, [isMobile, closeMobile]);

  return (
    <MobileNavOpenContext.Provider value={mobileOpened}>
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
          ref={navbarRef}
          id="app-navbar"
          p={{ base: 'xs', sm: 'md' }}
          styles={{
            navbar: {
              display: 'flex',
              flexDirection: 'column',
              overflow: isMobile ? 'auto' : 'hidden',
              ...(isMobile
                ? {
                    WebkitOverflowScrolling: 'touch',
                    overscrollBehaviorY: 'contain',
                  }
                : {}),
            },
          }}
        >
          <AppNavbar onNavigate={closeMobile} isMobileLayout={isMobile} />
        </AppShell.Navbar>

        <AppShell.Main>
          <Suspense fallback={<LoadingState />}>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/raids" element={<RaidsPage />} />
              <Route path="/nuke-targets" element={<NukeTargetsPage />} />
              <Route path="/reminders" element={<RemindersPage />} />
              <Route path="/builds" element={<BuildsPage />} />
              <Route path="/damage" element={<DamagePage />} />
              <Route path="/privacy" element={<PrivacyStoragePage />} />
              <Route path="/404" element={<NotFoundPage />} />
              <Route path="*" element={<Navigate to="/404" replace />} />
            </Routes>
          </Suspense>
        </AppShell.Main>
        <AppShell.Footer style={{ borderTop: 'none' }}>
          <AppFooter />
        </AppShell.Footer>
      </AppShell>
    </MobileNavOpenContext.Provider>
  );
}

export default App;
