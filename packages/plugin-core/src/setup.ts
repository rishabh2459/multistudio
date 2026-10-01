/**
 * Setup auto-fill (PL3): a first guess of who is who from file names and the
 * engine's layout, which the user confirms in the camera cards.
 */
import type {
  CameraLayoutIn,
  ClipRole,
  ProjectLayout,
  RoleIn,
  SessionOut,
  ShotType,
  SpeakerIn,
} from './types';

const WIDE = /(^|[^a-z])(wide|master|ws|group|all)([^a-z]|$)/i;
const BROLL = /(^|[^a-z])(b-?roll|cutaway|insert)([^a-z]|$)/i;

export function stem(path: string): string {
  const name = path.replace(/\\/g, '/').split('/').pop() ?? path;
  return name.replace(/\.[^.]+$/, '') || name;
}

/** "cam_A_host.mov" -> "Host"-ish label: drops camera words and separators. */
export function speakerName(path: string): string {
  const words = stem(path)
    .replace(/[_\-.]+/g, ' ')
    .split(/\s+/)
    .filter((w) => w && !/^(cam(era)?|a|b|c|d|\d+|mic|audio|track|ch\d*)$/i.test(w));
  const name = words.join(' ').trim() || stem(path);
  return name.charAt(0).toUpperCase() + name.slice(1);
}

export function guessRole(clip: { path: string; kind: 'video' | 'audio' }): ClipRole {
  if (clip.kind === 'audio') return 'mic';
  const s = stem(clip.path);
  if (BROLL.test(s)) return 'broll';
  if (WIDE.test(s)) return 'wide';
  return 'speaker';
}

/** Roles for a new session; keeps whatever the user already changed. */
export function defaultRoles(session: SessionOut): RoleIn[] {
  return session.clips.map((c) => {
    const role = c.role !== 'speaker' ? c.role : guessRole(c);
    return {
      clip_id: c.clip_id,
      role,
      speaker_label:
        role === 'speaker'
          ? c.label && c.label !== stem(c.path)
            ? c.label
            : speakerName(c.path)
          : null,
    };
  });
}

/** One camera card in the Setup form (advanced layout). */
export interface CameraCard {
  clipId: string;
  name: string;
  shot: ShotType;
  /** Speaker ids in frame. */
  covers: string[];
  priority: number;
}

export interface SpeakerRow {
  id: string;
  name: string;
  micClipId: string | null;
  micChannel: number | null;
}

/** Cards + speakers from the engine's current (effective) layout. */
export function cardsFromSession(session: SessionOut): {
  cameras: CameraCard[];
  speakers: SpeakerRow[];
} {
  const names = new Map(session.clips.map((c) => [c.clip_id, c.name]));
  return {
    speakers: session.speakers.map((s) => ({
      id: s.id,
      name: s.name,
      micClipId: s.mic_clip_id ?? null,
      micChannel: s.mic_channel ?? null,
    })),
    cameras: session.cameras.map((c) => ({
      clipId: c.clip_id,
      name: names.get(c.clip_id) ?? c.clip_id,
      shot: c.shot,
      covers: [...(c.covers ?? [])],
      priority: c.priority ?? 1,
    })),
  };
}

const SHOT_FOR_COUNT: ShotType[] = ['broll', 'solo', 'two', 'three', 'four'];

/** Shot type that matches how many speakers are in frame (user can override). */
export function shotFor(covers: number, everyone: number): ShotType {
  if (covers === 0) return 'broll';
  if (covers >= everyone && everyone > 1) return 'wide';
  return SHOT_FOR_COUNT[Math.min(covers, 4)] ?? 'wide';
}

/** The custom layout to send in `PATCH .../setup` (`layout`). */
export function layoutFromCards(cameras: CameraCard[], speakers: SpeakerRow[]): ProjectLayout {
  const out: { speakers: SpeakerIn[]; cameras: CameraLayoutIn[] } = {
    speakers: speakers.map((s) => ({
      id: s.id,
      name: s.name.trim() || 'Speaker',
      mic_clip_id: s.micClipId,
      mic_channel: s.micChannel,
    })),
    cameras: cameras
      .filter((c) => c.shot !== 'broll')
      .map((c) => ({ clip_id: c.clipId, shot: c.shot, covers: c.covers, priority: c.priority })),
  };
  return out;
}

/** Problems to show before running (the engine checks again). */
export function setupProblems(session: SessionOut): string[] {
  const problems: string[] = [];
  const offline = session.clips.filter((c) => c.file_status === 'missing');
  if (offline.length) problems.push(`Offline: ${offline.map((c) => c.name).join(', ')}`);
  if (!session.cameras.some((c) => c.shot !== 'broll')) problems.push('Mark at least one camera.');
  if (!session.speakers.length) problems.push('Name at least one speaker.');
  return problems;
}
