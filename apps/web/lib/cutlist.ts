/** Summaries of a cutlist for display (pure, unit-tested). */
import type { Clip, CutList } from './api';
import { framesToSeconds } from './format';

export interface CameraShare {
  clipId: string;
  name: string;
  seconds: number;
  fraction: number;
  shots: number;
}

export interface CutlistStats {
  shots: number;
  durationS: number;
  averageShotS: number;
  shortestShotS: number;
  cameras: CameraShare[];
}

export function clipDisplayName(clip: Pick<Clip, 'role' | 'speaker_label' | 'name'>): string {
  if (clip.role === 'wide') return `Wide (${clip.name})`;
  return clip.speaker_label || clip.name;
}

export function cutlistStats(cutlist: CutList, clips: Clip[]): CutlistStats {
  const names = new Map(clips.map((c) => [c.id, clipDisplayName(c)]));
  const segments = cutlist.segments;
  const totalFrames = segments.length ? segments[segments.length - 1]!.end_frame : 0;
  const byClip = new Map<string, { frames: number; shots: number }>();
  let shortest = Number.POSITIVE_INFINITY;
  for (const seg of segments) {
    const frames = seg.end_frame - seg.start_frame;
    shortest = Math.min(shortest, frames);
    const entry = byClip.get(seg.clip_id) ?? { frames: 0, shots: 0 };
    entry.frames += frames;
    entry.shots += 1;
    byClip.set(seg.clip_id, entry);
  }
  const durationS = framesToSeconds(totalFrames, cutlist.fps);
  const cameras = [...byClip.entries()]
    .map(([clipId, v]) => ({
      clipId,
      name: names.get(clipId) ?? 'Unknown camera',
      seconds: framesToSeconds(v.frames, cutlist.fps),
      fraction: totalFrames ? v.frames / totalFrames : 0,
      shots: v.shots,
    }))
    .sort((a, b) => b.seconds - a.seconds);
  return {
    shots: segments.length,
    durationS,
    averageShotS: segments.length ? durationS / segments.length : 0,
    shortestShotS: segments.length ? framesToSeconds(shortest, cutlist.fps) : 0,
    cameras,
  };
}

/** Sync confidence below this gets a warning in the UI (same as the engine). */
export const LOW_SYNC_CONFIDENCE = 0.5;

export type ClipReadiness = 'ok' | 'missing' | 'changed' | 'no-audio';

export function clipReadiness(clip: Clip): ClipReadiness {
  if (clip.file_status === 'missing') return 'missing';
  if (clip.file_status === 'changed') return 'changed';
  if (clip.media && !clip.media.audio_codec) return 'no-audio';
  return 'ok';
}

export function clipDurationS(clip: Clip): number | null {
  return clip.media ? framesToSeconds(clip.media.duration_frames, clip.media.fps) : null;
}
