/**
 * Helpers adapters use to turn an EditPlan into host operations. Pure functions,
 * so the timing logic is tested here once instead of in every host.
 */
import type { ApplyOptions, HostCaps } from './adapter';
import type { EditPlan, PlanMethod, Rational } from './types';

export const TICKS_PER_SECOND = 254_016_000_000n;

/** Exact Premiere ticks of a sequence frame (string: may exceed 2^53). */
export function frameToTicks(frame: number, fps: Rational): string {
  return ((BigInt(frame) * TICKS_PER_SECOND * BigInt(fps.den)) / BigInt(fps.num)).toString();
}

export function frameToSeconds(frame: number, fps: Rational): number {
  return (frame * fps.den) / fps.num;
}

/** Ticks as a string from a plan's integer tick field. */
export function ticks(value: number): string {
  return BigInt(Math.round(value)).toString();
}

/** HH:MM:SS:FF (non-drop display; for labels only). */
export function frameToTimecode(frame: number, fps: Rational): string {
  const base = Math.round(fps.num / fps.den);
  const ff = frame % base;
  const total = Math.floor(frame / base);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(Math.floor(total / 3600))}:${pad(Math.floor(total / 60) % 60)}:${pad(total % 60)}:${pad(ff)}`;
}

export interface ApplyDecision {
  via: 'native' | 'xml';
  method: PlanMethod;
  reason: string;
}

/** Native API calls or XML import, and the method the host can really do (7.2, Rule C). */
export function decideApply(
  plan: EditPlan,
  caps: HostCaps,
  opts: Partial<ApplyOptions> = {},
): ApplyDecision {
  const method = opts.method ?? plan.method ?? 'stacked_enable';
  const xml = caps.xmlImport !== null;
  if (opts.viaXml && xml) return { via: 'xml', method, reason: 'XML import requested' };
  if (method === 'multicam' && !caps.multicam) {
    return xml
      ? { via: 'xml', method, reason: 'this host builds multicam clips only through XML' }
      : {
          via: 'native',
          method: 'stacked_enable',
          reason: 'no multicam support: stacked tracks instead',
        };
  }
  if (method === 'stacked_enable' && !caps.enableDisable) {
    return xml
      ? { via: 'xml', method, reason: 'this host cannot disable clips through its API' }
      : { via: 'native', method: 'cuts', reason: 'no enable/disable: plain cuts instead' };
  }
  if (method === 'stacked_enable' && caps.stackedOneUndo === false && xml) {
    return {
      via: 'xml',
      method,
      reason: 'enable/disable in one undo step: XML import (clips arrive already disabled)',
    };
  }
  const reframed = plan.video_events.some(
    (e) => !!e.reframe && (e.reframe.scale !== 1 || !!e.reframe.path?.length),
  );
  if (reframed && !caps.keyframes && xml) {
    return { via: 'xml', method, reason: 'reframing needs keyframes: XML import' };
  }
  if (plan.video_events.length > caps.maxNativeEvents && xml) {
    return { via: 'xml', method, reason: `${plan.video_events.length} cuts: XML import is faster` };
  }
  return { via: 'native', method, reason: 'native apply' };
}

/** One clip to place on the host timeline. */
export interface PlaceOp {
  kind: 'video' | 'audio';
  track: number; // 1-based
  clipId: string;
  start: number; // sequence frames
  end: number;
  sourceInFrame: number;
  sourceInSample: number;
  sourceInTicks: number;
  enabled: boolean;
  gainDb?: number;
}

/** Every placement for a method, video first (by track, then time), then audio. */
export function placements(plan: EditPlan, method: PlanMethod): PlaceOp[] {
  const ops: PlaceOp[] = [];
  const piece = (p: {
    clip_id: string;
    start: number;
    end: number;
    source_in_frame: number;
    source_in_sample: number;
    source_in_ticks: number;
  }) => ({
    clipId: p.clip_id,
    start: p.start,
    end: p.end,
    sourceInFrame: p.source_in_frame,
    sourceInSample: p.source_in_sample,
    sourceInTicks: p.source_in_ticks,
  });
  if (method === 'cuts') {
    for (const ev of plan.video_events)
      ops.push({ kind: 'video', track: 1, enabled: true, ...piece(ev) });
  } else {
    for (const track of [...plan.video_tracks].sort((a, b) => a.index - b.index)) {
      for (const p of track.pieces) {
        ops.push({ kind: 'video', track: track.index, enabled: p.enabled, ...piece(p) });
      }
    }
  }
  for (const track of [...plan.audio_tracks].sort((a, b) => a.index - b.index)) {
    for (const p of track.pieces) {
      ops.push({
        kind: 'audio',
        track: track.index,
        enabled: true,
        gainDb: track.gain_db ?? 0,
        ...piece(p),
      });
    }
  }
  return ops;
}

export interface Lane {
  clipId: string;
  label: string;
  shot: string;
  /** [start, end) of the live pieces, as fractions 0..1 of the sequence. */
  live: { from: number; to: number; confidence: number | null }[];
  share: number; // fraction of the edit on this camera
}

/** Data for the mini multi-lane timeline in the plan preview. */
export function previewLanes(plan: EditPlan): Lane[] {
  const total = plan.sequence.duration_frames;
  const cams = plan.media
    .filter((m) => m.angle != null)
    .sort((a, b) => (a.angle ?? 0) - (b.angle ?? 0));
  return cams.map((m) => {
    const live = plan.video_events
      .filter((e) => e.clip_id === m.clip_id)
      .map((e) => ({ from: e.start / total, to: e.end / total, confidence: e.confidence ?? null }));
    return {
      clipId: m.clip_id,
      label: m.label || m.name,
      shot: m.shot,
      live,
      share: live.reduce((acc, p) => acc + (p.to - p.from), 0),
    };
  });
}

export interface PlanStats {
  cuts: number;
  durationS: number;
  averageShotS: number;
  lowConfidence: number;
  cameras: number;
}

export function planStats(plan: EditPlan): PlanStats {
  const fps = plan.sequence.fps;
  const durationS = frameToSeconds(plan.sequence.duration_frames, fps);
  return {
    cuts: Math.max(0, plan.video_events.length - 1),
    durationS,
    averageShotS: plan.video_events.length ? durationS / plan.video_events.length : 0,
    lowConfidence: plan.markers.filter((m) => m.kind === 'low_confidence').length,
    cameras: new Set(plan.video_events.map((e) => e.clip_id)).size,
  };
}
