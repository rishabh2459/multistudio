/**
 * Edit operations on a CutList. Pure functions: each returns a new cutlist and
 * keeps it valid (segments cover 0..end without gaps, neighbours never repeat a
 * camera). Edited segments are marked `source: 'manual'`.
 */
import type { CutList } from './api';

export type Segment = CutList['segments'][number];

function withSegments(cut: CutList, segments: Segment[]): CutList {
  return { ...cut, segments: normalize(segments) };
}

/** Merge neighbours showing the same camera and drop empty segments. */
export function normalize(segments: Segment[]): Segment[] {
  const out: Segment[] = [];
  for (const seg of segments) {
    if (seg.end_frame <= seg.start_frame) continue;
    const prev = out[out.length - 1];
    if (prev && prev.clip_id === seg.clip_id && !prev.reframe && !seg.reframe) {
      out[out.length - 1] = {
        ...prev,
        end_frame: seg.end_frame,
        source: prev.source === 'manual' || seg.source === 'manual' ? 'manual' : prev.source,
      };
    } else {
      out.push({ ...seg });
    }
  }
  return out;
}

export function durationFrames(cut: CutList): number {
  return cut.segments[cut.segments.length - 1]?.end_frame ?? 0;
}

/** Index of the segment containing `frame` (clamped to the timeline). */
export function segmentIndexAt(cut: CutList, frame: number): number {
  const segs = cut.segments;
  let lo = 0;
  let hi = segs.length - 1;
  const f = Math.min(Math.max(0, frame), durationFrames(cut) - 1);
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (segs[mid]!.start_frame <= f) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

/** Show `clipId` for the whole segment `index`. */
export function setCamera(cut: CutList, index: number, clipId: string): CutList {
  const seg = cut.segments[index];
  if (!seg || seg.clip_id === clipId) return cut;
  const segments = cut.segments.slice();
  segments[index] = { ...seg, clip_id: clipId, source: 'manual', reframe: null };
  return withSegments(cut, segments);
}

/** Cut at `frame` (no-op on an existing cut or outside the timeline). */
export function split(cut: CutList, frame: number): CutList {
  const index = segmentIndexAt(cut, frame);
  const seg = cut.segments[index]!;
  if (frame <= seg.start_frame || frame >= seg.end_frame) return cut;
  const segments = cut.segments.slice();
  segments.splice(
    index,
    1,
    { ...seg, end_frame: frame, source: 'manual' },
    { ...seg, start_frame: frame, source: 'manual' },
  );
  return { ...cut, segments }; // not normalized: the two halves share a camera on purpose
}

/**
 * Live switching: from `frame` on, show `clipId` until the next cut (what a
 * vision mixer does when you press a camera button during playback).
 */
export function switchAt(cut: CutList, frame: number, clipId: string): CutList {
  const index = segmentIndexAt(cut, frame);
  const seg = cut.segments[index]!;
  if (seg.clip_id === clipId) return cut;
  if (frame <= seg.start_frame) return setCamera(cut, index, clipId);
  return setCamera(split(cut, frame), index + 1, clipId);
}

/** Move the cut at the start of segment `index` (>= 1) to `frame`, keeping every
 *  segment at least `minFrames` long. */
export function moveCut(cut: CutList, index: number, frame: number, minFrames = 1): CutList {
  const prev = cut.segments[index - 1];
  const seg = cut.segments[index];
  if (!prev || !seg) return cut;
  const clamped = Math.round(
    Math.min(Math.max(frame, prev.start_frame + minFrames), seg.end_frame - minFrames),
  );
  if (clamped === seg.start_frame) return cut;
  const segments = cut.segments.slice();
  segments[index - 1] = { ...prev, end_frame: clamped, source: 'manual' };
  segments[index] = { ...seg, start_frame: clamped, source: 'manual' };
  return withSegments(cut, segments);
}

/** Remove the cut between segment `index` and the next one (the left camera stays). */
export function mergeWithNext(cut: CutList, index: number): CutList {
  const seg = cut.segments[index];
  const next = cut.segments[index + 1];
  if (!seg || !next) return cut;
  const segments = cut.segments.slice();
  segments.splice(index, 2, { ...seg, end_frame: next.end_frame, source: 'manual' });
  return withSegments(cut, segments);
}

/** Delete a shot: its time goes to the previous shot (or the next, for the first). */
export function removeSegment(cut: CutList, index: number): CutList {
  if (cut.segments.length < 2 || !cut.segments[index]) return cut;
  return index === 0 ? mergeWithNext(cutWithFirstAs(cut), 0) : mergeWithNext(cut, index - 1);
}

function cutWithFirstAs(cut: CutList): CutList {
  // The first shot takes the second one's camera, then they merge.
  const [first, second] = cut.segments;
  const segments = cut.segments.slice();
  segments[0] = { ...first!, clip_id: second!.clip_id, reframe: second!.reframe ?? null };
  return { ...cut, segments };
}

/** Cut positions (segment starts after 0). */
export function cutFrames(cut: CutList): number[] {
  return cut.segments.slice(1).map((s) => s.start_frame);
}

export function nextCut(cut: CutList, frame: number): number {
  return cutFrames(cut).find((f) => f > frame) ?? durationFrames(cut);
}

export function previousCut(cut: CutList, frame: number): number {
  const before = cutFrames(cut).filter((f) => f < frame);
  return before[before.length - 1] ?? 0;
}

/** Same segments (ignores version numbers): used to skip saving no-op edits. */
export function sameEdit(a: CutList, b: CutList): boolean {
  if (a.segments.length !== b.segments.length) return false;
  return a.segments.every((s, i) => {
    const t = b.segments[i]!;
    return (
      s.clip_id === t.clip_id && s.start_frame === t.start_frame && s.end_frame === t.end_frame
    );
  });
}
