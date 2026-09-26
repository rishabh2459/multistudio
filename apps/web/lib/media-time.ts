/** Timeline time <-> clip media time (see TimelineClip in the API). */
import type { TimelineClip } from './api';
import type { Rational } from './format';

export type ClipTiming = Pick<
  TimelineClip,
  'speed' | 'media_offset_s' | 'audio_offset_s' | 'duration_s'
>;

export function frameToSeconds(frame: number, fps: Rational): number {
  return (frame * fps.den) / fps.num;
}

export function secondsToFrame(seconds: number, fps: Rational): number {
  return Math.round((seconds * fps.num) / fps.den);
}

/** Seconds into the clip's file (and its proxy) shown at timeline time `t`. */
export function mediaTime(timing: ClipTiming, t: number): number {
  return t * timing.speed + timing.media_offset_s;
}

/** Was the camera recording at timeline time `t`? */
export function isRecording(timing: ClipTiming, t: number): boolean {
  const m = mediaTime(timing, t);
  return m >= 0 && m < timing.duration_s;
}

/** Timeline time of audio position `pos` (seconds since the clip's first sample). */
export function audioToTimeline(timing: ClipTiming, pos: number): number {
  return (pos - timing.audio_offset_s) / timing.speed;
}
