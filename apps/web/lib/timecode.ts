/** SMPTE timecode for display (same rules as the engine's export/timecode.py). */
import type { Rational } from './format';

export function isDropFrame(fps: Rational): boolean {
  return fps.den === 1001 && (fps.num === 30000 || fps.num === 60000);
}

/** Frame number -> "HH:MM:SS:FF" (";" before FF for drop-frame 29.97 / 59.94). */
export function frameToTimecode(frame: number, fps: Rational): string {
  const nominal = Math.round(fps.num / fps.den);
  const drop = isDropFrame(fps);
  let f = Math.max(0, Math.floor(frame));
  if (drop) {
    const d = (2 * nominal) / 30;
    const per10 = nominal * 600 - d * 9;
    const perMin = nominal * 60 - d;
    const tens = Math.floor(f / per10);
    const rem = f % per10;
    f += d * 9 * tens + (rem > d ? d * Math.floor((rem - d) / perMin) : 0);
  }
  const ff = f % nominal;
  const total = Math.floor(f / nominal);
  const pad = (n: number) => String(n).padStart(2, '0');
  const sep = drop ? ';' : ':';
  return `${pad(Math.floor(total / 3600) % 24)}:${pad(Math.floor(total / 60) % 60)}:${pad(total % 60)}${sep}${pad(ff)}`;
}
