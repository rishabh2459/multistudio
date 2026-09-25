/* eslint-disable */
/**
 * AUTO-GENERATED from schemas/multicam.schema.json (engine/src/multicam_engine/models) — do not edit by hand.
 * Regenerate with: make schemas
 */

export type AudioMode = "mix" | "single";
/**
 * This interface was referenced by `MulticamSchemas`'s JSON-Schema
 * via the `definition` "RemovalKind".
 */
export type RemovalKind = "filler" | "silence" | "manual";
export type SegmentSource = "auto" | "manual";
export type ClipRole = "speaker" | "wide" | "broll";
export type ClipRole1 = "speaker" | "wide" | "broll";
export type Preset = "calm" | "balanced" | "dynamic";
/**
 * This interface was referenced by `MulticamSchemas`'s JSON-Schema
 * via the `definition` "AudioMode".
 */
export type AudioMode1 = "mix" | "single";
/**
 * This interface was referenced by `MulticamSchemas`'s JSON-Schema
 * via the `definition` "ClipRole".
 */
export type ClipRole2 = "speaker" | "wide" | "broll";
/**
 * This interface was referenced by `MulticamSchemas`'s JSON-Schema
 * via the `definition` "Preset".
 */
export type Preset1 = "calm" | "balanced" | "dynamic";
/**
 * This interface was referenced by `MulticamSchemas`'s JSON-Schema
 * via the `definition` "SegmentSource".
 */
export type SegmentSource1 = "auto" | "manual";

/**
 * AUTO-GENERATED from multicam_engine models. Do not edit by hand.
 */
export interface MulticamSchemas {
  CutList?: CutList;
  GroundTruth?: GroundTruth;
  Project?: Project;
}
/**
 * This interface was referenced by `MulticamSchemas`'s JSON-Schema
 * via the `definition` "CutList".
 */
export interface CutList {
  audio: AudioConfig;
  fps: Rational;
  project_id: string;
  removals: Removal[];
  schema_version: 1;
  /**
   * @minItems 1
   */
  segments: [Segment, ...Segment[]];
  /**
   * Edit revision; bumps on every change
   */
  version: number;
}
/**
 * This interface was referenced by `MulticamSchemas`'s JSON-Schema
 * via the `definition` "AudioConfig".
 */
export interface AudioConfig {
  gains_db: {
    [k: string]: number | undefined;
  };
  mode: AudioMode;
  single_clip_id: string | null;
}
/**
 * An exact positive rational number, e.g. a frame rate of 30000/1001.
 *
 * This interface was referenced by `MulticamSchemas`'s JSON-Schema
 * via the `definition` "Rational".
 */
export interface Rational {
  den: number;
  num: number;
}
/**
 * This interface was referenced by `MulticamSchemas`'s JSON-Schema
 * via the `definition` "Removal".
 */
export interface Removal {
  approved: boolean;
  /**
   * Exclusive
   */
  end_frame: number;
  kind: RemovalKind;
  start_frame: number;
}
/**
 * This interface was referenced by `MulticamSchemas`'s JSON-Schema
 * via the `definition` "Segment".
 */
export interface Segment {
  clip_id: string;
  /**
   * Exclusive
   */
  end_frame: number;
  reframe: Reframe | null;
  source: SegmentSource;
  start_frame: number;
}
/**
 * Crop/zoom for a segment. Normalized coordinates (0..1) of the crop center.
 *
 * This interface was referenced by `MulticamSchemas`'s JSON-Schema
 * via the `definition` "Reframe".
 */
export interface Reframe {
  cx: number;
  cy: number;
  scale: number;
}
/**
 * This interface was referenced by `MulticamSchemas`'s JSON-Schema
 * via the `definition` "GroundTruth".
 */
export interface GroundTruth {
  /**
   * Window (reference timeline) where speech is fully labeled. None = whole recording. Speaker-accuracy is scored only inside it.
   */
  annotated_range: MsRange | null;
  /**
   * @minItems 2
   */
  clips: [GTClip, GTClip, ...GTClip[]];
  description: string;
  recording_id: string;
  reference_file: string;
  schema_version: 1;
  speech: SpeechTurn[];
}
/**
 * This interface was referenced by `MulticamSchemas`'s JSON-Schema
 * via the `definition` "MsRange".
 */
export interface MsRange {
  end_ms: number;
  start_ms: number;
}
/**
 * This interface was referenced by `MulticamSchemas`'s JSON-Schema
 * via the `definition` "GTClip".
 */
export interface GTClip {
  clap_end_ms: number | null;
  clap_start_ms: number;
  /**
   * File name inside the recording folder
   */
  file: string;
  role: ClipRole;
  speaker_label: string | null;
}
/**
 * This interface was referenced by `MulticamSchemas`'s JSON-Schema
 * via the `definition` "SpeechTurn".
 */
export interface SpeechTurn {
  end_ms: number;
  speaker_label: string;
  start_ms: number;
}
/**
 * This interface was referenced by `MulticamSchemas`'s JSON-Schema
 * via the `definition` "Project".
 */
export interface Project {
  clips: Clip[];
  created_at: string;
  id: string;
  name: string;
  output: OutputSettings;
  preset: Preset;
  reference_clip_id: string | null;
  schema_version: 1;
}
/**
 * This interface was referenced by `MulticamSchemas`'s JSON-Schema
 * via the `definition` "Clip".
 */
export interface Clip {
  id: string;
  media: MediaInfo | null;
  /**
   * Absolute path; files are referenced in place
   */
  path: string;
  role: ClipRole1;
  speaker_label: string | null;
  sync: SyncResult | null;
}
/**
 * Facts about a source file, read with ffprobe (Phase 1).
 *
 * This interface was referenced by `MulticamSchemas`'s JSON-Schema
 * via the `definition` "MediaInfo".
 */
export interface MediaInfo {
  audio_channels: number;
  audio_codec: string | null;
  audio_sample_rate: number | null;
  duration_frames: number;
  fps: Rational;
  height: number;
  is_vfr: boolean;
  video_codec: string;
  width: number;
}
/**
 * How a clip lines up with the project's reference clip.
 *
 * Sign convention (shared with ``benchmark.GroundTruth``):
 *     ``offset_samples`` = position of an event in THIS clip
 *                          minus position of the same event in the REFERENCE clip.
 *     Positive  -> this clip started recording EARLIER than the reference.
 *     Negative  -> this clip started recording LATER than the reference.
 *
 * ``drift_ppm``: how much faster this clip's clock runs than the reference,
 * in parts per million. A value of +100 means the clip accumulates 0.36 s
 * of extra duration per hour. This is a model parameter, not a timeline
 * position, so a float is acceptable here.
 *
 * This interface was referenced by `MulticamSchemas`'s JSON-Schema
 * via the `definition` "SyncResult".
 */
export interface SyncResult {
  confidence: number;
  drift_ppm: number;
  offset_samples: number;
  reference_clip_id: string;
  sample_rate: number;
}
/**
 * This interface was referenced by `MulticamSchemas`'s JSON-Schema
 * via the `definition` "OutputSettings".
 */
export interface OutputSettings {
  fps: Rational;
  height: number;
  width: number;
}
