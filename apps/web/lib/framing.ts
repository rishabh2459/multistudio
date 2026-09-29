/** Crop maths for previews (mirrors engine/reframe/framing.py and the render). */
import type { CutList } from './api';

export type Aspect = '16:9' | '9:16';
export type Reframe = NonNullable<CutList['segments'][number]['reframe']>;

export const ASPECT_SIZE: Record<Aspect, [number, number]> = {
  '16:9': [16, 9],
  '9:16': [9, 16],
};

/** Crop size as fractions of the source for an output shape and zoom. */
export function cropSize(
  srcW: number,
  srcH: number,
  outW: number,
  outH: number,
  scale: number,
): [number, number] {
  const src = srcW / srcH;
  const out = outW / outH;
  const [w, h] = out <= src ? [out / src, 1] : [1, src / out];
  return [w / scale, h / scale];
}

export function clampCenter(cx: number, cy: number, cw: number, ch: number): [number, number] {
  return [Math.min(Math.max(cx, cw / 2), 1 - cw / 2), Math.min(Math.max(cy, ch / 2), 1 - ch / 2)];
}

/** Crop centre at a timeline frame (linear between keyframes, held outside). */
export function centerAt(reframe: Reframe, frame: number): [number, number] {
  const keys = reframe.path;
  if (!keys || keys.length === 0) return [reframe.cx, reframe.cy];
  if (frame <= keys[0]!.frame) return [keys[0]!.cx, keys[0]!.cy];
  for (let i = 1; i < keys.length; i++) {
    const a = keys[i - 1]!;
    const b = keys[i]!;
    if (frame <= b.frame) {
      const f = (frame - a.frame) / (b.frame - a.frame);
      return [a.cx + (b.cx - a.cx) * f, a.cy + (b.cy - a.cy) * f];
    }
  }
  const last = keys[keys.length - 1]!;
  return [last.cx, last.cy];
}

/** The framing a segment uses for an output shape (portrait always crops). */
export function effectiveReframe(
  segment: CutList['segments'][number],
  aspect: Aspect,
): Reframe | null {
  if (aspect === '9:16')
    return segment.reframe_vertical ?? { cx: 0.5, cy: 0.5, scale: 1, path: null, manual: false };
  return segment.reframe ?? null;
}

/**
 * CSS (percent of the preview box) that shows only the crop of a video whose
 * box is scaled up: the preview box has the output's aspect ratio.
 */
export function cropStyle(
  reframe: Reframe,
  frame: number,
  srcW: number,
  srcH: number,
  aspect: Aspect,
): { width: string; height: string; left: string; top: string } {
  const [ow, oh] = ASPECT_SIZE[aspect];
  const [cw, ch] = cropSize(srcW, srcH, ow, oh, reframe.scale);
  const [cx, cy] = clampCenter(...centerAt(reframe, frame), cw, ch);
  const pct = (v: number) => `${(v * 100).toFixed(3)}%`;
  return {
    width: pct(1 / cw),
    height: pct(1 / ch),
    left: pct(-(cx - cw / 2) / cw),
    top: pct(-(cy - ch / 2) / ch),
  };
}
