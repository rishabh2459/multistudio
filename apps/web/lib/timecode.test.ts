import { frameToTimecode, isDropFrame } from './timecode';

describe('timecode display', () => {
  it('matches the engine (drop-frame at 29.97)', () => {
    const ntsc = { num: 30000, den: 1001 };
    expect(isDropFrame(ntsc)).toBe(true);
    expect(frameToTimecode(0, ntsc)).toBe('00:00:00;00');
    expect(frameToTimecode(1800, ntsc)).toBe('00:01:00;02');
    expect(frameToTimecode(17982, ntsc)).toBe('00:10:00;00');
    expect(frameToTimecode(107892, ntsc)).toBe('01:00:00;00');
    expect(frameToTimecode(3600, { num: 60000, den: 1001 })).toBe('00:01:00;04');
  });

  it('non-drop rates', () => {
    expect(frameToTimecode(25 * 3600 + 26, { num: 25, den: 1 })).toBe('01:00:01:01');
    expect(frameToTimecode(-5, { num: 25, den: 1 })).toBe('00:00:00:00');
  });
});
