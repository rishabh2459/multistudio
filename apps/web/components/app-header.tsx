'use client';

import { Clapperboard, Settings } from 'lucide-react';
import Link from 'next/link';

import { Badge } from '@/components/ui/badge';
import { buttonVariants } from '@/components/ui/button';
import { useHealth } from '@/lib/queries';

import { ThemeToggle } from './theme-toggle';

export function ApiStatus() {
  const health = useHealth();
  if (health.isPending) return <Badge variant="outline">Connecting…</Badge>;
  if (health.isError)
    return (
      <Badge variant="destructive" title={health.error.message}>
        Engine offline
      </Badge>
    );
  return (
    <Badge variant="success" title={`API ${health.data.version}`}>
      Engine ready
    </Badge>
  );
}

export function AppHeader() {
  return (
    <header className="sticky top-0 z-10 border-b bg-background/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <Clapperboard className="size-5 text-primary" aria-hidden />
          Multicam Studio
        </Link>
        <div className="ml-auto flex items-center gap-2">
          <ApiStatus />
          <ThemeToggle />
          <Link
            href="/settings/"
            aria-label="Settings"
            className={buttonVariants({ variant: 'ghost', size: 'icon' })}
          >
            <Settings />
          </Link>
        </div>
      </div>
    </header>
  );
}
