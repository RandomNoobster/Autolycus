import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';

import App from './App';
import { DISCORD_SESSION_QUERY_KEY } from './hooks/useSidebarDiscordSession';
import { theme } from './theme';
import type { ApiError } from './types';

import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';
import '@mantine/charts/styles.css';
import 'mantine-react-table/styles.css';
import './index.css';

/** A request said the Discord session is gone (logout in another tab, expiry): re-check it. */
function refreshSessionOnAuthError(error: unknown) {
  if ((error as Partial<ApiError> | null)?.code === 'AUTH_REQUIRED') {
    void queryClient.invalidateQueries({ queryKey: DISCORD_SESSION_QUERY_KEY });
  }
}

const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: refreshSessionOnAuthError }),
  mutationCache: new MutationCache({ onError: refreshSessionOnAuthError }),
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter useTransitions={false}>
        <MantineProvider theme={theme} defaultColorScheme="dark">
          <Notifications position="top-right" />
          <App />
        </MantineProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>
);
