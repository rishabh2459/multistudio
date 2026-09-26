import { makeCutlist } from '@/test/fixtures';

import {
  cutFrames,
  mergeWithNext,
  moveCut,
  nextCut,
  normalize,
  previousCut,
  removeSegment,
  sameEdit,
  segmentIndexAt,
  setCamera,
  split,
  switchAt,
} from './timeline-edit';

const base = () =>
  makeCutlist([
    ['a', 0, 100],
    ['b', 100, 250],
    ['a', 250, 400],
  ]);
const shape = (cut: ReturnType<typeof base>) =>
  cut.segments.map((s) => `${s.clip_id}:${s.start_frame}-${s.end_frame}`);

describe('timeline edits', () => {
  it('finds the shot at a frame', () => {
    const cut = base();
    expect([0, 99, 100, 399, 5000, -3].map((f) => segmentIndexAt(cut, f))).toEqual([
      0, 0, 1, 2, 2, 0,
    ]);
  });

  it('changes the camera of a shot and merges equal neighbours', () => {
    const cut = setCamera(base(), 1, 'a');
    expect(shape(cut)).toEqual(['a:0-400']);
    expect(cut.segments[0]!.source).toBe('manual');
    expect(setCamera(base(), 1, 'b')).toEqual(base()); // no change
  });

  it('switches camera from a frame on (live switching)', () => {
    expect(shape(switchAt(base(), 150, 'c'))).toEqual([
      'a:0-100',
      'b:100-150',
      'c:150-250',
      'a:250-400',
    ]);
    expect(shape(switchAt(base(), 100, 'c'))).toEqual(['a:0-100', 'c:100-250', 'a:250-400']);
    expect(shape(switchAt(base(), 150, 'a'))).toEqual(['a:0-100', 'b:100-150', 'a:150-400']);
    expect(switchAt(base(), 150, 'b')).toEqual(base());
  });

  it('splits and merges', () => {
    const cut = split(base(), 50);
    expect(shape(cut)).toEqual(['a:0-50', 'a:50-100', 'b:100-250', 'a:250-400']);
    expect(split(base(), 100)).toEqual(base()); // already a cut
    // a absorbs b, then touches the next a: one shot
    expect(shape(mergeWithNext(base(), 0))).toEqual(['a:0-400']);
  });

  it('moves a cut within its neighbours', () => {
    expect(shape(moveCut(base(), 1, 130))).toEqual(['a:0-130', 'b:130-250', 'a:250-400']);
    expect(shape(moveCut(base(), 1, -50))).toEqual(['a:0-1', 'b:1-250', 'a:250-400']);
    expect(shape(moveCut(base(), 1, 999))).toEqual(['a:0-249', 'b:249-250', 'a:250-400']);
    expect(shape(moveCut(base(), 2, 200, 10))).toEqual(['a:0-100', 'b:100-200', 'a:200-400']);
    expect(moveCut(base(), 0, 10)).toEqual(base()); // no cut before the first shot
  });

  it('removes shots', () => {
    expect(shape(removeSegment(base(), 1))).toEqual(['a:0-400']);
    expect(shape(removeSegment(base(), 0))).toEqual(['b:0-250', 'a:250-400']);
    const one = makeCutlist([['a', 0, 10]]);
    expect(removeSegment(one, 0)).toBe(one);
  });

  it('navigates cuts', () => {
    const cut = base();
    expect(cutFrames(cut)).toEqual([100, 250]);
    expect(nextCut(cut, 0)).toBe(100);
    expect(nextCut(cut, 250)).toBe(400);
    expect(previousCut(cut, 250)).toBe(100);
    expect(previousCut(cut, 50)).toBe(0);
  });

  it('keeps every edit valid: no gaps, no repeated cameras', () => {
    let cut = base();
    const ops = [
      (c: typeof cut) => switchAt(c, 37, 'c'),
      (c: typeof cut) => moveCut(c, 2, 90),
      (c: typeof cut) => split(c, 300),
      (c: typeof cut) => setCamera(c, 3, 'b'),
      (c: typeof cut) => removeSegment(c, 1),
      (c: typeof cut) => mergeWithNext(c, 0),
    ];
    for (const op of ops) {
      cut = op(cut);
      expect(cut.segments[0]!.start_frame).toBe(0);
      expect(cut.segments[cut.segments.length - 1]!.end_frame).toBe(400);
      cut.segments
        .slice(1)
        .forEach((s, i) => expect(s.start_frame).toBe(cut.segments[i]!.end_frame));
    }
    expect(normalize(cut.segments).length).toBeLessThanOrEqual(cut.segments.length);
    expect(sameEdit(cut, { ...cut, version: 99 })).toBe(true);
    expect(sameEdit(cut, base())).toBe(false);
  });
});
