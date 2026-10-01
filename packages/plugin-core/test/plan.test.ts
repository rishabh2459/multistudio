import { describe, expect, it } from 'vitest';

import type { HostCaps } from '../src/adapter';
import {
  decideApply,
  frameToSeconds,
  frameToTicks,
  frameToTimecode,
  placements,
  planStats,
  previewLanes,
} from '../src/plan';
import { loadPlan } from './helpers';

const NTSC = { num: 30000, den: 1001 };
const caps: HostCaps = {
  multicam: false,
  enableDisable: true,
  keyframes: false,
  markers: true,
  captions: false,
  xmlImport: 'xmeml',
  maxNativeEvents: 1500,
};

describe('time', () => {
  it('converts frames to exact Premiere ticks', () => {
    expect(frameToTicks(30000, NTSC)).toBe((1001n * 254016000000n).toString());
    expect(frameToTicks(1, { num: 25, den: 1 })).toBe('10160640000');
    // 10 hours at 29.97 does not lose precision (> 2^53 ticks)
    expect(frameToTicks(1078920, NTSC)).toBe('9144566855424000');
    expect(frameToSeconds(30000, NTSC)).toBe(1001);
    expect(frameToTimecode(30 * 61 + 5, { num: 30, den: 1 })).toBe('00:01:01:05');
  });
});

describe('decideApply', () => {
  const plan = loadPlan();
  it('applies natively by default', () => {
    expect(decideApply(plan, caps)).toEqual({
      via: 'native',
      method: 'stacked_enable',
      reason: 'native apply',
    });
  });
  it('uses XML for multicam when the host cannot build it', () => {
    expect(decideApply(plan, caps, { method: 'multicam' }).via).toBe('xml');
    expect(decideApply(plan, { ...caps, xmlImport: null }, { method: 'multicam' })).toMatchObject({
      via: 'native',
      method: 'stacked_enable',
    });
  });
  it('falls back to cuts without enable/disable, and XML for huge edits', () => {
    expect(decideApply(plan, { ...caps, enableDisable: false, xmlImport: null })).toMatchObject({
      method: 'cuts',
    });
    expect(decideApply(plan, { ...caps, maxNativeEvents: 3 }).via).toBe('xml');
    expect(decideApply(plan, caps, { viaXml: true }).via).toBe('xml');
  });
});

describe('placements', () => {
  const plan = loadPlan();
  it('cuts: the live events on track 1', () => {
    const video = placements(plan, 'cuts').filter((o) => o.kind === 'video');
    expect(video).toHaveLength(plan.video_events.length);
    expect(video.every((o) => o.track === 1 && o.enabled)).toBe(true);
    expect(video[0]!.start).toBe(0);
    expect(video.at(-1)!.end).toBe(plan.sequence.duration_frames);
  });
  it('stacked: every camera on its own track, exactly one live piece at a time', () => {
    const video = placements(plan, 'stacked_enable').filter((o) => o.kind === 'video');
    expect(new Set(video.map((o) => o.track))).toEqual(new Set([1, 2, 3]));
    const live = video.filter((o) => o.enabled).sort((a, b) => a.start - b.start);
    expect(live.map((o) => [o.start, o.end, o.clipId])).toEqual(
      plan.video_events.map((e) => [e.start, e.end, e.clip_id]),
    );
  });
  it('audio tracks follow with their gain', () => {
    const audio = placements(plan, 'cuts').filter((o) => o.kind === 'audio');
    expect(audio.length).toBeGreaterThan(0);
    expect(audio.every((o) => typeof o.gainDb === 'number')).toBe(true);
  });
});

describe('preview', () => {
  it('lanes cover the whole edit once', () => {
    const plan = loadPlan();
    const lanes = previewLanes(plan);
    expect(lanes.map((l) => l.label)).toHaveLength(3);
    const share = lanes.reduce((a, l) => a + l.share, 0);
    expect(share).toBeCloseTo(1, 6);
    const stats = planStats(plan);
    expect(stats.cuts).toBe(plan.video_events.length - 1);
    expect(stats.durationS).toBeGreaterThan(30);
  });
});
