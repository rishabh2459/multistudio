/**
 * The part of Resolve's scripting API this plugin uses, as exposed to Workflow
 * Integration plugins (`WorkflowIntegration.GetResolve()`, Studio only). Same names
 * as the Python API; calls may return values or promises, so every call is awaited.
 */
type MaybePromise<T> = T | Promise<T>;

export interface MediaPoolItem {
  GetClipProperty(key: string): MaybePromise<string | Record<string, string>>;
  GetUniqueId(): MaybePromise<string>;
}

export interface TimelineItem {
  GetStart(): MaybePromise<number>;
  GetDuration(): MaybePromise<number>;
  GetLeftOffset(): MaybePromise<number>;
  GetMediaPoolItem(): MaybePromise<MediaPoolItem | null>;
  SetClipEnabled?(enabled: boolean): MaybePromise<boolean>;
}

export interface Timeline {
  GetName(): MaybePromise<string>;
  GetUniqueId(): MaybePromise<string>;
  GetSetting(key: string): MaybePromise<string>;
  GetStartFrame(): MaybePromise<number>;
  GetTrackCount(kind: 'video' | 'audio'): MaybePromise<number>;
  GetItemListInTrack(kind: 'video' | 'audio', index: number): MaybePromise<TimelineItem[] | null>;
  AddTrack(kind: 'video' | 'audio', subType?: string): MaybePromise<boolean>;
  AddMarker(
    frame: number,
    color: string,
    name: string,
    note: string,
    duration: number,
    customData: string,
  ): MaybePromise<boolean>;
}

export interface Folder {
  GetClipList(): MaybePromise<MediaPoolItem[] | null>;
  GetSubFolderList(): MaybePromise<Folder[] | null>;
}

export interface ClipInfo {
  mediaPoolItem: MediaPoolItem;
  startFrame: number;
  endFrame: number;
  trackIndex: number;
  recordFrame: number;
  mediaType: 1 | 2;
}

export interface MediaPool {
  GetRootFolder(): MaybePromise<Folder>;
  ImportMedia(paths: string[]): MaybePromise<MediaPoolItem[] | null>;
  CreateEmptyTimeline(name: string): MaybePromise<Timeline | null>;
  AppendToTimeline(infos: ClipInfo[]): MaybePromise<TimelineItem[] | null>;
  ImportTimelineFromFile(
    path: string,
    options: Record<string, unknown>,
  ): MaybePromise<Timeline | null>;
}

export interface Project {
  GetMediaPool(): MaybePromise<MediaPool>;
  GetCurrentTimeline(): MaybePromise<Timeline | null>;
  SetCurrentTimeline(tl: Timeline): MaybePromise<boolean>;
  GetSetting(key: string): MaybePromise<string>;
}

export interface Resolve {
  GetProjectManager(): MaybePromise<{ GetCurrentProject(): MaybePromise<Project | null> }>;
  GetVersionString(): MaybePromise<string>;
}
