import { makeClip, makeCutlist } from '@/test/fixtures';

import { clipDisplayName, clipReadiness, cutlistStats } from './cutlist';

describe('cutlist helpers', () => {
  const host = makeClip({ id: 'a', speaker_label: 'Host' });
  const guest = makeClip({ id: 'b', name: 'cam2.mp4' });
  const wide = makeClip({ id: 'w', name: 'wide.mp4', role: 'wide' });

  it('names cameras for people', () => {
    expect(clipDisplayName(host)).toBe('Host');
    expect(clipDisplayName(guest)).toBe('cam2.mp4');
    expect(clipDisplayName(wide)).toBe('Wide (wide.mp4)');
  });

  it('summarizes shots and camera shares', () => {
    const cut = makeCutlist([
      ['a', 0, 90],
      ['b', 90, 150],
      ['a', 150, 240],
      ['w', 240, 300],
    ]);
    const stats = cutlistStats(cut, [host, guest, wide]);
    expect(stats.shots).toBe(4);
    expect(stats.durationS).toBe(10);
    expect(stats.averageShotS).toBe(2.5);
    expect(stats.shortestShotS).toBe(2);
    expect(stats.cameras[0]).toMatchObject({ clipId: 'a', name: 'Host', seconds: 6, shots: 2 });
    expect(stats.cameras.reduce((sum, c) => sum + c.fraction, 0)).toBeCloseTo(1);
  });

  it('reports clips that need attention', () => {
    expect(clipReadiness(host)).toBe('ok');
    expect(clipReadiness(makeClip({ file_status: 'missing' }))).toBe('missing');
    expect(clipReadiness(makeClip({ file_status: 'changed' }))).toBe('changed');
    const silent = makeClip();
    silent.media = { ...silent.media!, audio_codec: null };
    expect(clipReadiness(silent)).toBe('no-audio');
  });
});
