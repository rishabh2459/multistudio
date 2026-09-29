import { makeCutlist } from '@/test/fixtures';

import {
  centerAt,
  clampCenter,
  cropSize,
  cropStyle,
  effectiveReframe,
  type Reframe,
} from './framing';

const still = (cx: number, cy: number, scale = 1): Reframe => ({
  cx,
  cy,
  scale,
  path: null,
  manual: false,
});

describe('cropSize', () => {
  it('keeps the full frame for the same shape', () => {
    expect(cropSize(1920, 1080, 16, 9, 1)).toEqual([1, 1]);
  });
  it('crops a narrow column for vertical output', () => {
    const [w, h] = cropSize(1920, 1080, 9, 16, 1);
    expect(h).toBe(1);
    expect(w).toBeCloseTo(0.31640625, 6);
  });
  it('shrinks with zoom', () => {
    expect(cropSize(1920, 1080, 16, 9, 2)).toEqual([0.5, 0.5]);
  });
});

describe('clampCenter', () => {
  it('keeps the crop inside the frame', () => {
    expect(clampCenter(0.05, 0.99, 0.5, 0.5)).toEqual([0.25, 0.75]);
    expect(clampCenter(0.4, 0.6, 0.5, 0.5)).toEqual([0.4, 0.6]);
  });
});

describe('centerAt', () => {
  const moving: Reframe = {
    ...still(0.5, 0.5),
    path: [
      { frame: 10, cx: 0.2, cy: 0.5 },
      { frame: 20, cx: 0.6, cy: 0.3 },
    ],
  };
  it('holds before the first and after the last key', () => {
    expect(centerAt(moving, 0)).toEqual([0.2, 0.5]);
    expect(centerAt(moving, 99)).toEqual([0.6, 0.3]);
  });
  it('interpolates between keys', () => {
    const [x, y] = centerAt(moving, 15);
    expect(x).toBeCloseTo(0.4);
    expect(y).toBeCloseTo(0.4);
  });
  it('uses the still centre without a path', () => {
    expect(centerAt(still(0.3, 0.7), 5)).toEqual([0.3, 0.7]);
  });
});

describe('effectiveReframe', () => {
  const seg = makeCutlist([['a', 0, 100]]).segments[0]!;
  it('has no crop for 16:9 by default and a centred one for 9:16', () => {
    expect(effectiveReframe(seg, '16:9')).toBeNull();
    expect(effectiveReframe(seg, '9:16')).toMatchObject({ cx: 0.5, cy: 0.5, scale: 1 });
  });
  it('picks the framing of the chosen shape', () => {
    const framed = { ...seg, reframe: still(0.4, 0.5, 1.3), reframe_vertical: still(0.7, 0.5) };
    expect(effectiveReframe(framed, '16:9')?.scale).toBe(1.3);
    expect(effectiveReframe(framed, '9:16')?.cx).toBe(0.7);
  });
});

describe('cropStyle', () => {
  it('scales and offsets the video so only the crop shows', () => {
    const style = cropStyle(still(0.75, 0.5, 2), 0, 1920, 1080, '16:9');
    expect(style).toEqual({
      width: '200.000%',
      height: '200.000%',
      left: '-100.000%',
      top: '-50.000%',
    });
  });
  it('is the whole video at 1x in the same shape', () => {
    expect(cropStyle(still(0.5, 0.5), 0, 1920, 1080, '16:9')).toEqual({
      width: '100.000%',
      height: '100.000%',
      left: '0.000%',
      top: '0.000%',
    });
  });
});
