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
      duration_frames: 1800,
      width: 1920,
      height: 1080,
      video_codec: 'h264',
      audio_codec: 'aac',
      audio_sample_rate: 48000,
      audio_channels: 2,
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
