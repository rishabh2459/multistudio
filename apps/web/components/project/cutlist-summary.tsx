import type { Clip, CutList } from '@/lib/api';
import { cutlistStats } from '@/lib/cutlist';
import { formatDuration, formatPercent } from '@/lib/format';

const CAM_COLORS = ['bg-cam-1', 'bg-cam-2', 'bg-cam-3', 'bg-cam-4'];

export function cameraColor(clips: Clip[], clipId: string): string {
  const i = clips.findIndex((c) => c.id === clipId);
  return CAM_COLORS[(i < 0 ? 0 : i) % CAM_COLORS.length]!;
}

/** Timeline strip: one colored block per shot. */
export function CutlistTimeline({ cutlist, clips }: { cutlist: CutList; clips: Clip[] }) {
  const total = cutlist.segments.at(-1)?.end_frame ?? 0;
  if (!total) return null;
  return (
    <div
      className="flex h-6 w-full overflow-hidden rounded-md bg-muted"
      role="img"
      aria-label={`Timeline with ${cutlist.segments.length} shots`}
    >
      {cutlist.segments.map((seg) => (
        <div
          key={seg.start_frame}
          className={cameraColor(clips, seg.clip_id)}
          style={{ width: `${((seg.end_frame - seg.start_frame) / total) * 100}%` }}
        />
      ))}
    </div>
  );
}

export function CutlistSummary({ cutlist, clips }: { cutlist: CutList; clips: Clip[] }) {
  const stats = cutlistStats(cutlist, clips);
  return (
    <div className="flex flex-col gap-4" data-testid="cutlist-summary">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ['Length', formatDuration(stats.durationS)],
          ['Shots', String(stats.shots)],
          ['Average shot', `${stats.averageShotS.toFixed(1)} s`],
          ['Shortest shot', `${stats.shortestShotS.toFixed(1)} s`],
        ].map(([term, value]) => (
          <div key={term} className="rounded-lg bg-muted/60 p-3">
            <dt className="text-xs text-muted-foreground">{term}</dt>
            <dd className="text-lg font-semibold tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      <CutlistTimeline cutlist={cutlist} clips={clips} />
      <ul className="flex flex-col gap-1.5 text-sm">
        {stats.cameras.map((cam) => (
          <li key={cam.clipId} className="flex items-center gap-2">
            <span className={`size-3 rounded-sm ${cameraColor(clips, cam.clipId)}`} aria-hidden />
            <span className="flex-1 truncate">{cam.name}</span>
            <span className="tabular-nums text-muted-foreground">
              {formatPercent(cam.fraction)} · {cam.shots} shots
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
