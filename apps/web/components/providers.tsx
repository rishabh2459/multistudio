'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, useState, type ReactNode } from 'react';

import { ApiError } from '@/lib/api';
import { useSettings, type Theme } from '@/lib/settings-store';

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 2_000,
        refetchOnWindowFocus: true,
        // A 4xx will not fix itself; an unreachable API might (it may be starting).
        retry: (failures, error) =>
          !(error instanceof ApiError && error.status >= 400 && error.status < 500) && failures < 2,
      },
    },
  });
}

export function applyTheme(theme: Theme, prefersDark: boolean): void {
  const dark = theme === 'dark' || (theme === 'system' && prefersDark);
  document.documentElement.classList.toggle('dark', dark);
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light';
}

function ThemeSync() {
  const theme = useSettings((s) => s.theme);
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const sync = () => applyTheme(theme, media.matches);
    sync();
    media.addEventListener('change', sync);
    return () => media.removeEventListener('change', sync);
  }, [theme]);
  return null;
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(makeQueryClient);
  // Load saved settings (API address, token, theme) before anything talks to the API.
  const [ready, setReady] = useState(false);
  useEffect(() => {
    void Promise.resolve(useSettings.persist.rehydrate()).finally(() => setReady(true));
  }, []);
  return (
    <QueryClientProvider client={client}>
      {ready && <ThemeSync />}
      {ready ? children : null}
    </QueryClientProvider>
  );
}
