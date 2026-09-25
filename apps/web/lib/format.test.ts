import {
  formatBytes,
  formatDuration,
  formatFps,
  formatOffsetMs,
  formatPercent,
  formatRelative,
  framesToSeconds,
  joinPath,
  slug,
} from './format';

describe('format', () => {
  it('formats frame rates', () => {
    expect(formatFps({ num: 30000, den: 1001 })).toBe('29.97');
    expect(formatFps({ num: 25, den: 1 })).toBe('25');
  });

  it('formats durations', () => {
    expect(formatDuration(65)).toBe('1:05');
    expect(formatDuration(3725.4)).toBe('1:02:05');
    expect(formatDuration(0)).toBe('0:00');
    expect(formatDuration(Number.NaN)).toBe('–');
  });

  it('converts frames to seconds exactly for NTSC rates', () => {
    expect(framesToSeconds(30000, { num: 30000, den: 1001 })).toBeCloseTo(1001);
  });

  it('formats percentages, offsets and sizes', () => {
    expect(formatPercent(0.456)).toBe('46%');
    expect(formatPercent(1.2)).toBe('100%');
    expect(formatOffsetMs(1000)).toBe('+1000.0 ms');
    expect(formatOffsetMs(-12.54)).toBe('−12.5 ms');
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(1536)).toBe('1.5 KB');
    expect(formatBytes(250 * 1024 * 1024)).toBe('250 MB');
  });

  it('formats relative times', () => {
    const now = new Date('2026-01-01T12:00:00Z');
    expect(formatRelative('2026-01-01T11:59:50Z', now)).toBe('just now');
    expect(formatRelative('2026-01-01T11:55:00Z', now)).toBe('5 min ago');
    expect(formatRelative('2026-01-01T09:00:00Z', now)).toBe('3 h ago');
  });

  it('joins paths with the folder separator and makes safe names', () => {
    expect(joinPath('/Users/me/Videos/', 'a.mp4')).toBe('/Users/me/Videos/a.mp4');
    expect(joinPath('C:\\Videos', 'a.mp4')).toBe('C:\\Videos\\a.mp4');
    expect(slug('Episode 12: Guest / Talk')).toBe('Episode-12-Guest-Talk');
    expect(slug('???')).toBe('episode');
  });
});
