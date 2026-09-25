import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { AppHeader } from '@/components/app-header';
import { Providers } from '@/components/providers';

import './globals.css';

export const metadata: Metadata = {
  title: 'Multicam Studio',
  description: 'Sync multi-camera recordings by audio and cut to whoever is speaking.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background text-foreground antialiased">
        <Providers>
          <AppHeader />
          <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
