/** Small formatting helpers (pure, unit-tested). */

export interface Rational {
  num: number;
  den: number;
}

export function fpsValue(fps: Rational): number {
  return fps.num / fps.den;
}

/** 29.97, 25, 59.94 ... (two decimals only when needed). */
export function formatFps(fps: Rational): string {
  const v = fpsValue(fps);
  return Number.isInteger(v) ? String(v) : v.toFixed(2);
}

/** 3725.4 s -> "1:02:05", 65 s -> "1:05". */
export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '–';
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const ss = String(s).padStart(2, '0');
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
}

export function framesToSeconds(frames: number, fps: Rational): number {
  return (frames * fps.den) / fps.num;
}

export function formatPercent(fraction: number, digits = 0): string {
  const clamped = Math.min(1, Math.max(0, fraction));
  return `${(clamped * 100).toFixed(digits)}%`;
}

/** Signed milliseconds: "+1000.0 ms", "-12.5 ms". */
export function formatOffsetMs(ms: number): string {
  const sign = ms > 0 ? '+' : ms < 0 ? '−' : '';
  return `${sign}${Math.abs(ms).toFixed(1)} ms`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = bytes / 1024;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[i]}`;
}

/** "just now", "5 min ago", "3 h ago", "2 d ago", else a date. */
export function formatRelative(iso: string, now: Date = new Date()): string {
  const then = new Date(iso);
  const seconds = Math.round((now.getTime() - then.getTime()) / 1000);
  if (seconds < 45) return 'just now';
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  if (seconds < 86400 * 7) return `${Math.round(seconds / 86400)} d ago`;
  return then.toLocaleDateString();
}

/** Join a folder and a file name with the folder's own separator. */
export function joinPath(folder: string, name: string): string {
  const sep = folder.includes('\\') && !folder.includes('/') ? '\\' : '/';
  return folder.replace(/[\\/]+$/, '') + sep + name;
}

export function slug(text: string): string {
  return (
    text
      .trim()
      .replace(/[^A-Za-z0-9._-]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'episode'
  );
}
