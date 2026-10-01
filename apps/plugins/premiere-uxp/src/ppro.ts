/**
 * The part of Premiere's UXP DOM (`require('premierepro')`, 25.6+) this plugin uses,
 * typed from Adobe's reference (checked 2026-10-01). Keeping it to an interface lets
 * the adapter run against a mock in tests; the PL4 spike confirms it in Premiere.
 *
 * Rules from the reference: actions are created inside `project.lockedAccess()` and
 * inside the `executeTransaction` callback (26.3+), one transaction = one undo step.
 */

export interface TickTime {
  readonly ticks: string;
  readonly ticksNumber: number;
  readonly seconds: number;
}

export interface TickTimeStatic {
  createWithTicks(ticks: string): TickTime;
  createWithSeconds(seconds: number): TickTime;
}

export interface Action {
  readonly __action?: true;
}

export interface CompoundAction {
  addAction(action: Action): boolean;
}

export interface Guid {
  toString(): string;
}

export interface ProjectItem {
  readonly name: string;
  getId?(): string;
}

export interface ClipProjectItem extends ProjectItem {
  getMediaFilePath(): Promise<string>;
  createSetInOutPointsAction(inPoint: TickTime, outPoint: TickTime): Action;
  createClearInOutPointsAction(): Action;
  isSequence(): Promise<boolean>;
}

export interface ClipTrackItem {
  getName(): Promise<string>;
  getStartTime(): Promise<TickTime>;
  getEndTime(): Promise<TickTime>;
  getInPoint(): Promise<TickTime>;
  getOutPoint(): Promise<TickTime>;
  getProjectItem(): Promise<ProjectItem>;
  getTrackIndex(): Promise<number>;
  isDisabled?(): Promise<boolean>;
  createSetDisabledAction?(disabled: boolean): Action;
}

export interface Track {
  readonly name: string;
  getTrackItems(trackItemType: number, includeEmptyTrackItems: boolean): ClipTrackItem[];
  getIndex(): Promise<number>;
}

export interface RectF {
  width: number;
  height: number;
}

export interface Sequence {
  readonly guid: Guid;
  readonly name: string;
  getVideoTrackCount(): Promise<number>;
  getVideoTrack(index: number): Promise<Track>;
  getAudioTrackCount(): Promise<number>;
  getAudioTrack(index: number): Promise<Track>;
  getTimebase(): Promise<string>; // ticks per frame
  getFrameSize(): Promise<RectF>;
  getEndTime(): Promise<TickTime>;
}

export interface SequenceEditor {
  createOverwriteItemAction(
    projectItem: ProjectItem,
    time: TickTime,
    videoTrackIndex: number,
    audioTrackIndex: number,
  ): Action;
}

export interface Markers {
  createAddMarkerAction(
    name: string,
    markerType: string,
    startTime: TickTime,
    duration: TickTime,
    comments?: string,
  ): Action;
}

export interface FolderItem extends ProjectItem {
  getItems(): Promise<ProjectItem[]>;
}

export interface Project {
  readonly name: string;
  readonly path?: string;
  getActiveSequence(): Promise<Sequence | null>;
  getSequences(): Promise<Sequence[]>;
  openSequence(sequence: Sequence): Promise<boolean>;
  setActiveSequence(sequence: Sequence): Promise<boolean>;
  importFiles(
    paths: string[],
    suppressUI: boolean,
    targetBin: ProjectItem | null,
    asNumberedStills: boolean,
  ): Promise<boolean>;
  createSequence(name: string, presetPath?: string): Promise<Sequence>;
  getRootItem(): Promise<FolderItem>;
  getInsertionBin(): Promise<ProjectItem>;
  executeTransaction(callback: (compound: CompoundAction) => void, undoString: string): boolean;
  lockedAccess(callback: () => void): void;
}

export interface PremierePro {
  Project: { getActiveProject(): Promise<Project | null> };
  TickTime: TickTimeStatic;
  SequenceEditor: { getEditor(sequence: Sequence): SequenceEditor };
  Markers: { getMarkers(owner: Sequence): Promise<Markers> };
  ClipProjectItem: { cast(item: ProjectItem): ClipProjectItem };
  Constants: { TrackItemType: { CLIP: number }; MarkerType?: { COMMENT?: string } };
}

/** UXP host modules this plugin uses (`require('uxp')`, `require('os')`). */
export interface UxpHost {
  readFile(path: string): Promise<string | null>;
  openExternal(url: string): Promise<void>;
  homedir(): string;
  platform(): 'mac' | 'windows';
  appVersion: string;
}
