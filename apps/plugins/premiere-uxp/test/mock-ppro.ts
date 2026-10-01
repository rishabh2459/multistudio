/**
 * A small fake of Premiere's UXP DOM that enforces the documented rules: actions
 * are created only inside project.lockedAccess() + executeTransaction(), and each
 * transaction is one undo step.
 */
import type {
  Action,
  ClipProjectItem,
  ClipTrackItem,
  CompoundAction,
  PremierePro,
  Project,
  ProjectItem,
  Sequence,
  TickTime,
  Track,
  UxpHost,
} from '../src/ppro';

export const TPS = 254016000000n;

export function tt(ticks: bigint | string): TickTime {
  const t = BigInt(ticks);
  return { ticks: t.toString(), ticksNumber: Number(t), seconds: Number(t) / Number(TPS) };
}

interface Rules {
  locked: boolean;
  inTransaction: boolean;
}

export interface RecordedAction extends Action {
  kind: string;
  args: unknown[];
}

class FakeClip implements ClipProjectItem {
  constructor(
    readonly name: string,
    readonly path: string,
    private readonly rules: Rules,
    readonly sequence = false,
  ) {}
  getId() {
    return `id:${this.name}`;
  }
  async getMediaFilePath() {
    return this.path;
  }
  async isSequence() {
    return this.sequence;
  }
  createSetInOutPointsAction(i: TickTime, o: TickTime): Action {
    return act(this.rules, 'setInOut', [this.name, i.ticks, o.ticks]);
  }
  createClearInOutPointsAction(): Action {
    return act(this.rules, 'clearInOut', [this.name]);
  }
}

function act(rules: Rules, kind: string, args: unknown[]): RecordedAction {
  if (!rules.locked || !rules.inTransaction) {
    throw new Error(
      `Script action failed to execute (${kind} created outside lockedAccess/transaction)`,
    );
  }
  return { kind, args };
}

export class FakeTrackItem implements ClipTrackItem {
  disabled = false;
  constructor(
    readonly item: FakeClip,
    readonly start: bigint,
    readonly end: bigint,
    readonly inPoint: bigint,
    readonly track: number,
    private readonly rules: Rules,
  ) {}
  async getName() {
    return this.item.name;
  }
  async getStartTime() {
    return tt(this.start);
  }
  async getEndTime() {
    return tt(this.end);
  }
  async getInPoint() {
    return tt(this.inPoint);
  }
  async getOutPoint() {
    return tt(this.inPoint + this.end - this.start);
  }
  async getProjectItem() {
    return this.item;
  }
  async getTrackIndex() {
    return this.track;
  }
  createSetDisabledAction(disabled: boolean): Action {
    const a = act(this.rules, 'setDisabled', [this.item.name, disabled]);
    (a as RecordedAction & { apply?: () => void }).apply = () => (this.disabled = disabled);
    return a;
  }
}

class FakeTrack implements Track {
  items: FakeTrackItem[] = [];
  constructor(
    readonly name: string,
    private readonly index: number,
  ) {}
  getTrackItems() {
    return this.items;
  }
  async getIndex() {
    return this.index;
  }
}

export class FakeSequence implements Sequence {
  video: FakeTrack[] = [];
  audio: FakeTrack[] = [];
  constructor(
    readonly name: string,
    readonly guid = { toString: () => `guid:${name}` },
    readonly timebase = '8475667200',
    readonly size = { width: 1920, height: 1080 },
  ) {}
  async getVideoTrackCount() {
    return this.video.length;
  }
  async getVideoTrack(i: number) {
    return this.video[i]!;
  }
  async getAudioTrackCount() {
    return this.audio.length;
  }
  async getAudioTrack(i: number) {
    return this.audio[i]!;
  }
  async getTimebase() {
    return this.timebase;
  }
  async getFrameSize() {
    return this.size;
  }
  async getEndTime() {
    return tt(0n);
  }
  track(kind: 'video' | 'audio', i: number): FakeTrack {
    const list = kind === 'video' ? this.video : this.audio;
    while (list.length <= i)
      list.push(new FakeTrack(`${kind[0]!.toUpperCase()}${list.length + 1}`, list.length));
    return list[i]!;
  }
}

export class FakeProject implements Project {
  readonly name = 'Podcast.prproj';
  rules: Rules = { locked: false, inTransaction: false };
  sequences: FakeSequence[] = [];
  active: FakeSequence | null = null;
  clips: FakeClip[] = [];
  transactions: { undo: string; actions: RecordedAction[] }[] = [];
  imported: string[] = [];
  opened: string[] = [];
  onImport: ((path: string) => FakeSequence | null) | null = null;

  addClip(name: string, path: string): FakeClip {
    const c = new FakeClip(name, path, this.rules);
    this.clips.push(c);
    return c;
  }
  place(
    seq: FakeSequence,
    kind: 'video' | 'audio',
    track: number,
    clip: FakeClip,
    startF: number,
    inF: number,
    lenF: number,
  ) {
    const tpf = BigInt(seq.timebase);
    seq
      .track(kind, track)
      .items.push(
        new FakeTrackItem(
          clip,
          BigInt(startF) * tpf,
          BigInt(startF + lenF) * tpf,
          BigInt(inF) * tpf,
          track,
          this.rules,
        ),
      );
  }
  async getActiveSequence() {
    return this.active;
  }
  async getSequences() {
    return this.sequences;
  }
  async openSequence(s: Sequence) {
    this.opened.push(s.name);
    return true;
  }
  async setActiveSequence() {
    return true;
  }
  async importFiles(paths: string[]) {
    this.imported.push(...paths);
    const seq = this.onImport?.(paths[0]!);
    if (seq) this.sequences.push(seq);
    return true;
  }
  async createSequence(name: string) {
    const seq = new FakeSequence(name);
    this.sequences.push(seq);
    return seq;
  }
  async getRootItem() {
    const clips = this.clips;
    return {
      name: 'root',
      getItems: async () => [
        { name: 'Media', getItems: async () => clips as ProjectItem[] } as unknown as ProjectItem,
      ],
    };
  }
  async getInsertionBin() {
    return { name: 'root' } as ProjectItem;
  }
  lockedAccess(cb: () => void) {
    this.rules.locked = true;
    try {
      cb();
    } finally {
      this.rules.locked = false;
    }
  }
  executeTransaction(cb: (c: CompoundAction) => void, undo: string) {
    if (!this.rules.locked) throw new Error('executeTransaction outside lockedAccess');
    const actions: RecordedAction[] = [];
    this.rules.inTransaction = true;
    try {
      cb({ addAction: (a) => (actions.push(a as RecordedAction), true) });
    } finally {
      this.rules.inTransaction = false;
    }
    for (const a of actions) (a as RecordedAction & { apply?: () => void }).apply?.();
    this.transactions.push({ undo, actions });
    return true;
  }
}

export function fakePpro(project: FakeProject): PremierePro {
  return {
    Project: { getActiveProject: async () => project },
    TickTime: {
      createWithTicks: (t: string) => tt(t),
      createWithSeconds: (s: number) => tt(BigInt(Math.round(s * Number(TPS)))),
    },
    SequenceEditor: {
      getEditor: (seq: Sequence) => ({
        createOverwriteItemAction: (item: ProjectItem, time: TickTime, v: number, a: number) => {
          const rec = act(project.rules, 'overwrite', [item.name, time.ticks, v, a]);
          (rec as RecordedAction & { apply?: () => void }).apply = () => {
            const s = seq as FakeSequence;
            if (v >= 0)
              s.track('video', v).items.push(
                new FakeTrackItem(
                  item as FakeClip,
                  BigInt(time.ticks),
                  BigInt(time.ticks) + 1n,
                  0n,
                  v,
                  project.rules,
                ),
              );
          };
          return rec;
        },
      }),
    },
    Markers: {
      getMarkers: async () => ({
        createAddMarkerAction: (
          name: string,
          type: string,
          start: TickTime,
          dur: TickTime,
          comments?: string,
        ) => act(project.rules, 'marker', [name, type, start.ticks, dur.ticks, comments]),
      }),
    },
    ClipProjectItem: { cast: (item: ProjectItem) => item as ClipProjectItem },
    Constants: { TrackItemType: { CLIP: 1 }, MarkerType: { COMMENT: 'Comment' } },
  };
}

export const uxpHost: UxpHost = {
  appVersion: '26.1.0',
  platform: () => 'mac',
  homedir: () => '/Users/editor',
  readFile: async () => null,
  openExternal: async () => undefined,
};
