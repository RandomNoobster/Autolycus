import { Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from '@mantine/core';

import { AppNavbar } from '@/components/layout/AppNavbar';
import { AppHeader } from '@/components/layout/AppHeader';
import { RaidsPage } from '@/pages/RaidsPage';
import { BuildsPage } from '@/pages/BuildsPage';
import { DamagePage } from '@/pages/DamagePageView';
import { HomePage } from '@/pages/HomePage';
import { TokenRequestPage } from '@/pages/TokenRequestPage';
import { NotFoundPage } from '@/pages/NotFoundPage';

function App() {
  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{
        width: 250,
        breakpoint: 'sm',
      }}
      padding="md"
    >
      <AppShell.Header>
        <AppHeader />
      </AppShell.Header>

      <AppShell.Navbar p="md">
        <AppNavbar />
      </AppShell.Navbar>

      <AppShell.Main>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/token-request" element={<TokenRequestPage />} />
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
