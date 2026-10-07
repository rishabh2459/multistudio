/**
 * Wire types of the Plugin API v1, generated from the engine (`make schemas`).
 * Never hand-write a shape the engine already defines.
 */
import type { Schema } from '@multicam/types/api';

export type Handshake = Schema<'Handshake'>;
export type SessionCreate = Schema<'SessionCreate'>;
export type SessionClipIn = Schema<'SessionClipIn'>;
export type SessionOut = Schema<'SessionOut'>;
export type SessionClipOut = Schema<'SessionClipOut'>;
export type SessionSetup = Schema<'SessionSetup'>;
export type SessionState = Schema<'SessionState'>;
export type RoleIn = Schema<'RoleIn'>;
export type RunIn = Schema<'RunIn'>;
export type RunOut = Schema<'RunOut'>;
export type PlanSummary = Schema<'PlanSummary'>;
export type ExportFileOut = Schema<'ExportFileOut'>;
export type FeedbackOut = Schema<'FeedbackOut'>;
export type PresetOut = Schema<'PresetOut'>;
export type HostApp = Schema<'HostApp'>;
export type PlanMethod = Schema<'PlanMethod'>;
export type ClipRole = Schema<'ClipRole'>;
export type Preset = Schema<'Preset'>;

export type EditPlan = Schema<'EditPlan-Output'>;
export type PlanMedia = Schema<'PlanMedia-Output'>;
export type VideoEvent = Schema<'VideoEvent-Output'>;
export type VideoTrack = Schema<'VideoTrack-Output'>;
export type TrackPiece = Schema<'TrackPiece-Output'>;
export type AudioTrack = Schema<'AudioTrack-Output'>;
export type PlanPiece = Schema<'PlanPiece'>;
export type PlanMarker = Schema<'PlanMarker-Output'>;
export type PlanOverlay = Schema<'PlanOverlay-Output'>;
export type PlanTransformKey = Schema<'PlanTransformKey'>;
export type Rational = Schema<'Rational'>;
export type ShotType = Schema<'ShotType'>;
export type ProjectLayout = Schema<'ProjectLayout'>;
export type SpeakerIn = Schema<'Speaker-Input'>;
export type CameraLayoutIn = Schema<'CameraLayout-Input'>;

/** Stable error codes (`ErrorCode` in plugin_schemas.py) plus client-side ones. */
export type ErrorCode =
  | 'media_offline'
  | 'unsupported_codec'
  | 'sync_low_confidence'
  | 'no_speech'
  | 'setup_required'
  | 'no_plan'
  | 'not_found'
  | 'invalid_request'
  | 'not_available'
  | 'engine_busy'
  | 'licence_required'
  | 'job_failed'
  // client side
  | 'engine_unreachable'
  | 'engine_incompatible'
  | 'unauthorized'
  | 'host_error';
