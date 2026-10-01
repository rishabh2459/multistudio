/** Test data shaped exactly like the API's responses. */
import type { Clip, CutList, Job, Project } from '@/lib/api';

const FPS = { num: 30, den: 1 };
export const T0 = '2026-01-01T12:00:00Z';

export function makeClip(over: Partial<Clip> = {}): Clip {
  return {
    id: 'clip-1',
    project_id: 'proj-1',
    path: '/rec/cam1.mp4',
    name: 'cam1.mp4',
    role: 'speaker',
    speaker_label: null,
    media: {
      fps: FPS,
      is_vfr: false,
      has_video: true,
      duration_frames: 1800,
      width: 1920,
      height: 1080,
      video_codec: 'h264',
      audio_codec: 'aac',
      audio_sample_rate: 48000,
      audio_channels: 2,
      start_timecode: null,
    },
    sync: null,
    file_status: 'ok',
    is_reference: false,
    ...over,
  };
}

export function makeProject(over: Partial<Project> = {}): Project {
  return {
    id: 'proj-1',
    name: 'Episode 1',
    preset: 'balanced',
    output: { fps: FPS, width: 1920, height: 1080 },
    output_custom: false,
    reference_clip_id: null,
    clips: [],
    speakers: [],
    cameras: [],
    layout_custom: false,
    switch: {
      min_shot_s: 2.5,
      switch_delay_s: 0.7,
      bridge_gap_s: 0.7,
      lead_s: 0.15,
      crosstalk_to_wide_s: 1.2,
      silence_to_wide_s: 3.0,
      max_shot_s: 0,
      wide_frequency: 0.3,
      group_reward: 0.7,
    },
    switch_custom: false,
    cutlist_version: null,
    created_at: T0,
    updated_at: T0,
    ...over,
  };
}

export function makeCutlist(segments: Array<[string, number, number]>): CutList {
  return {
    schema_version: 1,
    version: 1,
    project_id: 'proj-1',
    fps: FPS,
    segments: segments.map(([clip_id, start_frame, end_frame]) => ({
      clip_id,
      start_frame,
      end_frame,
      source: 'auto',
      reframe: null,
      reframe_vertical: null,
      confidence: null,
    })),
    removals: [],
    audio: { mode: 'mix', gains_db: {}, single_clip_id: null },
  };
}

export function makeJob(over: Partial<Job> = {}): Job {
  return {
    id: 'job-1',
    project_id: 'proj-1',
    kind: 'auto',
    status: 'running',
    stage: 'sync',
    progress: 0.3,
    message: '',
    params: {},
    result: null,
    error: null,
    retry_of: null,
    created_at: T0,
    started_at: T0,
    finished_at: null,
    ...over,
  };
}
