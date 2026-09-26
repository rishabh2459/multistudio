/** Keyboard shortcuts of the timeline editor (pure: key -> action). */

export type EditorAction =
  | { type: 'camera'; index: number } // 0-based camera number
  | { type: 'togglePlay' }
  | { type: 'play'; faster: boolean } // L (again = faster)
  | { type: 'pause' } // K
  | { type: 'back'; seconds: number } // J
  | { type: 'step'; frames: number }
  | { type: 'jumpCut'; direction: 1 | -1 }
  | { type: 'home' }
  | { type: 'end' }
  | { type: 'split' }
  | { type: 'delete' }
  | { type: 'undo' }
  | { type: 'redo' }
  | { type: 'zoom'; factor: number };

export interface KeyInput {
  key: string;
  code: string;
  shiftKey: boolean;
  metaKey: boolean;
  ctrlKey: boolean;
  altKey: boolean;
}

export const SHORTCUTS: [string, string][] = [
  ['1 – 9', 'Switch to that camera from the playhead'],
  ['Space', 'Play / pause'],
  ['J / K / L', 'Back 5 s / pause / play (again: faster)'],
  ['← →', 'One frame (Shift: previous / next cut)'],
  ['S', 'Cut at the playhead'],
  ['Delete', 'Remove the selected shot'],
  ['⌘Z / ⇧⌘Z', 'Undo / redo (Ctrl on Windows)'],
  ['+ / −', 'Zoom'],
];

export function actionForKey(e: KeyInput): EditorAction | null {
  const mod = e.metaKey || e.ctrlKey;
  if (mod && !e.altKey) {
    const k = e.key.toLowerCase();
    if (k === 'z') return e.shiftKey ? { type: 'redo' } : { type: 'undo' };
    if (k === 'y') return { type: 'redo' };
    return null;
  }
  if (e.altKey) return null;
  const digit = /^Digit([1-9])$/.exec(e.code) ?? /^Numpad([1-9])$/.exec(e.code);
  if (digit) return { type: 'camera', index: Number(digit[1]) - 1 };
  switch (e.key) {
    case ' ':
      return { type: 'togglePlay' };
    case 'k':
    case 'K':
      return { type: 'pause' };
    case 'l':
    case 'L':
      return { type: 'play', faster: true };
    case 'j':
    case 'J':
      return { type: 'back', seconds: 5 };
    case 'ArrowLeft':
      return e.shiftKey ? { type: 'jumpCut', direction: -1 } : { type: 'step', frames: -1 };
    case 'ArrowRight':
      return e.shiftKey ? { type: 'jumpCut', direction: 1 } : { type: 'step', frames: 1 };
    case 'Home':
      return { type: 'home' };
    case 'End':
      return { type: 'end' };
    case 's':
    case 'S':
      return { type: 'split' };
    case 'Delete':
    case 'Backspace':
      return { type: 'delete' };
    case '+':
    case '=':
      return { type: 'zoom', factor: 1.5 };
    case '-':
    case '_':
      return { type: 'zoom', factor: 1 / 1.5 };
    default:
      return null;
  }
}

/** Shortcuts must not fire while the user types in a field. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
}
