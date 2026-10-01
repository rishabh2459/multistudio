/** A fake Resolve scripting API (async, as WI plugins see it). */
import type {
  ClipInfo,
  Folder,
  MediaPool,
  MediaPoolItem,
  Project,
  Resolve,
  Timeline,
  TimelineItem,
} from '../src/resolve-api';

export class FakeMpi implements MediaPoolItem {
  constructor(
    readonly path: string,
    readonly type = 'Video + Audio',
  ) {}
  async GetClipProperty(key: string) {
    return key === 'File Path' ? this.path : key === 'Type' ? this.type : '';
  }
  async GetUniqueId() {
    return `mpi:${this.path.split('/').pop()}`;
  }
}

export class FakeItem implements TimelineItem {
  enabled = true;
  constructor(
    readonly mpi: FakeMpi,
    readonly start: number,
    readonly duration: number,
    readonly left = 0,
    readonly info: ClipInfo | null = null,
  ) {}
  async GetStart() {
    return this.start;
  }
  async GetDuration() {
    return this.duration;
  }
  async GetLeftOffset() {
    return this.left;
  }
  async GetMediaPoolItem() {
    return this.mpi;
  }
  async SetClipEnabled(on: boolean) {
    this.enabled = on;
    return true;
  }
}

export class FakeTimeline implements Timeline {
  tracks: Record<'video' | 'audio', FakeItem[][]> = { video: [[]], audio: [[]] };
  markers: unknown[][] = [];
  constructor(
    public name: string,
    readonly startFrame = 107892,
  ) {}
  async GetName() {
    return this.name;
  }
  async GetUniqueId() {
    return `tl:${this.name}`;
  }
  async GetSetting(key: string) {
    return key === 'timelineFrameRate' ? '29.97' : '';
  }
  async GetStartFrame() {
    return this.startFrame;
  }
  async GetTrackCount(kind: 'video' | 'audio') {
    return this.tracks[kind].length;
  }
  async GetItemListInTrack(kind: 'video' | 'audio', i: number) {
    return this.tracks[kind][i - 1] ?? [];
  }
  async AddTrack(kind: 'video' | 'audio') {
    this.tracks[kind].push([]);
    return true;
  }
  async AddMarker(...args: unknown[]) {
    this.markers.push(args);
    return true;
  }
  put(kind: 'video' | 'audio', track: number, item: FakeItem) {
    while (this.tracks[kind].length < track) this.tracks[kind].push([]);
    this.tracks[kind][track - 1]!.push(item);
  }
}

export class FakeProject implements Project {
  timelines: FakeTimeline[] = [];
  current: FakeTimeline | null = null;
  clips: FakeMpi[] = [];
  appends: ClipInfo[][] = [];
  importedXml: string[] = [];
  async GetMediaPool(): Promise<MediaPool> {
    const root: Folder = {
      GetClipList: async () => [],
      GetSubFolderList: async () => [
        { GetClipList: async () => this.clips, GetSubFolderList: async () => [] },
      ],
    };
    return {
      GetRootFolder: async () => root,
      ImportMedia: async (paths: string[]) => {
        const added = paths.map((p) => new FakeMpi(p));
        this.clips.push(...added);
        return added;
      },
      CreateEmptyTimeline: async (name: string) => {
        if (this.timelines.some((t) => t.name === name)) return null;
        const tl = new FakeTimeline(name);
        this.timelines.push(tl);
        return tl;
      },
      AppendToTimeline: async (infos: ClipInfo[]) => {
        this.appends.push(infos);
        const tl = this.current!;
        return infos.map((info) => {
          const kind = info.mediaType === 1 ? 'video' : 'audio';
          if (info.trackIndex > tl.tracks[kind].length) throw new Error('no such track');
          const item = new FakeItem(
            info.mediaPoolItem as FakeMpi,
            info.recordFrame,
            info.endFrame - info.startFrame + 1,
            info.startFrame,
            info,
          );
          tl.put(kind, info.trackIndex, item);
          return item;
        });
      },
      ImportTimelineFromFile: async (path: string, options: Record<string, unknown>) => {
        this.importedXml.push(path);
        const tl = new FakeTimeline(String(options.timelineName));
        this.timelines.push(tl);
        return tl;
      },
    };
  }
  async GetCurrentTimeline() {
    return this.current;
  }
  async SetCurrentTimeline(tl: Timeline) {
    this.current = tl as FakeTimeline;
    return true;
  }
  async GetSetting(key: string) {
    return (
      (
        {
          timelineResolutionWidth: '1280',
          timelineResolutionHeight: '720',
          timelineFrameRate: '29.97',
        } as Record<string, string>
      )[key] ?? ''
    );
  }
}

export function fakeResolve(project: FakeProject | null): Resolve {
  return {
    GetProjectManager: async () => ({ GetCurrentProject: async () => project }),
    GetVersionString: async () => '20.1.0',
  };
}

export function podcast(
  paths: { cam1: string; cam2: string; wide: string },
  opts: { synced?: boolean; name?: string; mic?: string } = {},
) {
  const project = new FakeProject();
  const tl = new FakeTimeline(opts.name ?? 'Ep 42');
  project.timelines.push(tl);
  project.current = tl;
  const s = tl.startFrame;
  const synced = opts.synced ?? true;
  const [c1, c2, w] = [paths.cam1, paths.cam2, paths.wide].map((p) => new FakeMpi(p));
  project.clips.push(c1!, c2!, w!);
  tl.put('video', 1, new FakeItem(c1!, s, 900));
  tl.put('video', 2, new FakeItem(c2!, s, 900, synced ? 30 : 0));
  tl.put('video', 3, new FakeItem(w!, s + (synced ? 15 : 0), 900));
  tl.put('audio', 1, new FakeItem(c1!, s, 900));
  if (opts.mic) {
    const m = new FakeMpi(opts.mic, 'Audio');
    project.clips.push(m);
    tl.put('audio', 4, new FakeItem(m, s, 900));
  }
  return project;
}
