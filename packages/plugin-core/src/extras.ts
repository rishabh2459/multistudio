/**
 * Wire types of the social-clip and jump-cut endpoints (Plugin API 1.x, additive).
 *
 * These mirror apps/api plugin_schemas.py (SocialIn/SocialOut, JumpCutIn,
 * RemovalsOut). They are written by hand so the plugin builds before
 * `make schemas` regenerates @multicam/types; keep them in step with the Python.
 */
import type { EditPlan } from './types';

export type SocialAspect = '16:9' | '4:5' | '9:16' | '1:1';
export type Corner = 'top_left' | 'top_right' | 'bottom_left' | 'bottom_right' | 'center';

export interface WatermarkIn {
  path: string;
  corner?: Corner;
  /** Width as a fraction of the frame width (default 0.18). */
  size?: number;
  opacity?: number;
  margin?: number;
}

export interface EndPageIn {
  path: string;
  seconds?: number;
}

export interface SocialIn {
  in_frame: number;
  out_frame: number;
  aspects: SocialAspect[];
  name?: string;
  watermark?: WatermarkIn | null;
  end_page?: EndPageIn | null;
  jump_cuts?: boolean;
  version?: number;
  xml?: boolean;
}

export interface SocialClipOut {
  aspect: SocialAspect;
  name: string;
  width: number;
  height: number;
  duration_frames: number;
  plan: EditPlan;
  xml_path: string | null;
  render_path: string;
}

export interface SocialOut {
  clips: SocialClipOut[];
  export_dir: string;
  warnings: string[];
}

export type JumpCutMode = 'db' | 'vad';

export interface JumpCutIn {
  /** `db`: AutoPod-style loudness cutoff; `vad`: speech detection (noisy rooms). */
  mode?: JumpCutMode;
  /** Everyone below this level (dBFS) counts as silence (db mode). */
  threshold_db?: number;
  /** Per-mic cutoffs, keyed by the mic's clip id (db mode). */
  mic_threshold_db?: Record<string, number>;
  /** Only pauses at least this long are cut. */
  min_silence_s?: number;
  /** Silence kept before and after the speech around each cut. */
  pad_s?: number;
  /** Cuts shorter than this (after padding) are skipped. */
  min_removal_s?: number;
}

export interface RemovalOut {
  index: number;
  start: number;
  end: number;
  kind: string;
  approved: boolean;
  seconds: number;
}

export interface RemovalsOut {
  cutlist_version: number;
  duration_frames: number;
  removed_frames: number;
  removed_seconds: number;
  removals: RemovalOut[];
}

export interface RemovalsPatch {
  approve?: number[];
  reject?: number[];
  /** true / false: approve / reject every removal first. */
  all?: boolean | null;
}

/** EditPlan fields added in 1.x that older generated types may not have yet. */
export interface PlanExtras {
  aspect?: string | null;
  rippled?: boolean;
  overlays?: unknown[];
}

export type PlanWithExtras = EditPlan & PlanExtras;
