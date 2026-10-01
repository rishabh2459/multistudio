/**
 * plugin-core primitives as UXP Spectrum widgets (sp-button, sp-picker ...), so the
 * shared panel looks native in Premiere. Events are wired with listeners: UXP widgets
 * fire DOM events React does not map.
 */
import { useEffect, useRef, type ReactNode } from 'react';

import type { Primitives } from '@multicam/plugin-core/ui';

type Widget = Record<string, unknown> & { ref?: unknown; children?: ReactNode; style?: object };

declare module 'react' {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      'sp-button': Widget;
      'sp-textfield': Widget;
      'sp-picker': Widget;
      'sp-menu': Widget;
      'sp-menu-item': Widget;
      'sp-slider': Widget;
      'sp-checkbox': Widget;
      'sp-progressbar': Widget;
      'sp-label': Widget;
    }
  }
}

function useListener(event: string, handler: (e: Event) => void) {
  const ref = useRef<HTMLElement | null>(null);
  const saved = useRef(handler);
  saved.current = handler;
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const fn = (e: Event) => saved.current(e);
    el.addEventListener(event, fn);
    return () => el.removeEventListener(event, fn);
  }, [event]);
  return ref;
}

const value = (e: Event) => (e.target as unknown as { value: string }).value;

function Button(p: {
  children: ReactNode;
  onClick: () => void;
  variant?: string;
  disabled?: boolean;
}) {
  const ref = useListener('click', () => !p.disabled && p.onClick());
  return (
    <sp-button
      ref={ref}
      variant={p.variant === 'secondary' || !p.variant ? 'secondary' : 'cta'}
      disabled={p.disabled ? true : undefined}
    >
      {p.children}
    </sp-button>
  );
}

export const spectrumPrimitives: Primitives = {
  Button,
  TextField: (p) => {
    const ref = useListener('input', (e) => p.onChange(value(e)));
    return (
      <sp-textfield
        ref={ref}
        value={p.value}
        disabled={p.disabled ? true : undefined}
        style={{ width: '100%' }}
      >
        <sp-label slot="label">{p.label}</sp-label>
      </sp-textfield>
    );
  },
  Select: (p) => {
    const ref = useListener('change', (e) => p.onChange(value(e)));
    return (
      <sp-picker
        ref={ref}
        label={p.label}
        value={p.value}
        disabled={p.disabled ? true : undefined}
        style={{ width: '100%' }}
      >
        <sp-menu slot="options">
          {p.options.map((o) => (
            <sp-menu-item
              key={o.value}
              value={o.value}
              selected={o.value === p.value ? true : undefined}
            >
              {o.label}
            </sp-menu-item>
          ))}
        </sp-menu>
      </sp-picker>
    );
  },
  Slider: (p) => {
    const ref = useListener('change', (e) => p.onChange(Number(value(e))));
    return (
      <sp-slider
        ref={ref}
        min={p.min}
        max={p.max}
        step={p.step}
        value={p.value}
        disabled={p.disabled ? true : undefined}
        style={{ width: '100%' }}
      >
        <sp-label slot="label">
          {p.label}: {p.format ? p.format(p.value) : p.value}
        </sp-label>
      </sp-slider>
    );
  },
  Checkbox: (p) => {
    const ref = useListener('change', (e) =>
      p.onChange(!!(e.target as unknown as { checked: boolean }).checked),
    );
    return (
      <sp-checkbox
        ref={ref}
        checked={p.value ? true : undefined}
        disabled={p.disabled ? true : undefined}
      >
        {p.label}
      </sp-checkbox>
    );
  },
  Progress: (p) => (
    <sp-progressbar max={100} value={Math.round(p.value * 100)} style={{ width: '100%' }}>
      <sp-label slot="label">{p.label}</sp-label>
    </sp-progressbar>
  ),
};
