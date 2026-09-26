import { actionForKey, isTypingTarget, type KeyInput } from './editor-keys';

const key = (k: string, code = '', mods: Partial<KeyInput> = {}): KeyInput => ({
  key: k,
  code,
  shiftKey: false,
  metaKey: false,
  ctrlKey: false,
  altKey: false,
  ...mods,
});

describe('editor shortcuts', () => {
  it('maps keys to actions', () => {
    expect(actionForKey(key('2', 'Digit2'))).toEqual({ type: 'camera', index: 1 });
    expect(actionForKey(key('@', 'Digit2', { shiftKey: true }))).toEqual({
      type: 'camera',
      index: 1,
    });
    expect(actionForKey(key('9', 'Numpad9'))).toEqual({ type: 'camera', index: 8 });
    expect(actionForKey(key('0', 'Digit0'))).toBeNull();
    expect(actionForKey(key(' '))).toEqual({ type: 'togglePlay' });
    expect(actionForKey(key('l'))).toEqual({ type: 'play', faster: true });
    expect(actionForKey(key('k'))).toEqual({ type: 'pause' });
    expect(actionForKey(key('j'))).toEqual({ type: 'back', seconds: 5 });
    expect(actionForKey(key('ArrowRight'))).toEqual({ type: 'step', frames: 1 });
    expect(actionForKey(key('ArrowLeft', '', { shiftKey: true }))).toEqual({
      type: 'jumpCut',
      direction: -1,
    });
    expect(actionForKey(key('s'))).toEqual({ type: 'split' });
    expect(actionForKey(key('Backspace'))).toEqual({ type: 'delete' });
    expect(actionForKey(key('='))).toEqual({ type: 'zoom', factor: 1.5 });
  });

  it('undo / redo with Cmd or Ctrl; other modified keys are left to the app', () => {
    expect(actionForKey(key('z', 'KeyZ', { metaKey: true }))).toEqual({ type: 'undo' });
    expect(actionForKey(key('Z', 'KeyZ', { metaKey: true, shiftKey: true }))).toEqual({
      type: 'redo',
    });
    expect(actionForKey(key('y', 'KeyY', { ctrlKey: true }))).toEqual({ type: 'redo' });
    expect(actionForKey(key('c', 'KeyC', { metaKey: true }))).toBeNull();
    expect(actionForKey(key('1', 'Digit1', { altKey: true }))).toBeNull();
  });

  it('does not steal keys from text fields', () => {
    expect(isTypingTarget(document.createElement('input'))).toBe(true);
    expect(isTypingTarget(document.createElement('select'))).toBe(true);
    expect(isTypingTarget(document.createElement('div'))).toBe(false);
    expect(isTypingTarget(null)).toBe(false);
  });
});
