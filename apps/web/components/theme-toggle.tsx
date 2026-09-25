'use client';

import { Monitor, Moon, Sun } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useSettings, type Theme } from '@/lib/settings-store';

const NEXT: Record<Theme, Theme> = { system: 'light', light: 'dark', dark: 'system' };
const ICON = { system: Monitor, light: Sun, dark: Moon };

export function ThemeToggle() {
  const theme = useSettings((s) => s.theme);
  const update = useSettings((s) => s.update);
  const Icon = ICON[theme];
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={`Theme: ${theme} (click to change)`}
      title={`Theme: ${theme}`}
      onClick={() => update({ theme: NEXT[theme] })}
    >
      <Icon />
    </Button>
  );
}
