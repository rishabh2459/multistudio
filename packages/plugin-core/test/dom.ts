/** jsdom globals when the runner has no DOM environment (vitest sets it up itself). */
import { JSDOM } from 'jsdom';

if (typeof (globalThis as { document?: unknown }).document === 'undefined') {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost/' });
  const g = globalThis as Record<string, unknown>;
  for (const key of [
    'window',
    'document',
    'navigator',
    'HTMLElement',
    'Node',
    'Event',
    'MouseEvent',
    'getComputedStyle',
    'MutationObserver',
    'HTMLInputElement',
    'HTMLSelectElement',
    'Element',
    'requestAnimationFrame',
  ]) {
    if (!(key in g) || key === 'navigator') {
      try {
        g[key] = (dom.window as unknown as Record<string, unknown>)[key];
      } catch {
        Object.defineProperty(g, key, {
          value: (dom.window as unknown as Record<string, unknown>)[key],
          configurable: true,
        });
      }
    }
  }
}
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
