'use client';

import { useEffect, useRef } from 'react';

import type { ClipTiming } from '@/lib/media-time';

/**
 * Draws a clip's waveform for the visible part of the timeline only (a canvas
 * cannot be an hour wide). `left` / `width` are the visible pixels of the lane.
 */
export function WaveformCanvas({
  peaks,
  rate,
  timing,
  zoom,
  left,
  width,
  height,
}: {
  peaks: Uint8Array | undefined;
  rate: number;
  timing: ClipTiming;
  zoom: number;
  left: number;
  width: number;
  height: number;
}) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(width * dpr));
    canvas.height = Math.max(1, Math.round(height * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    if (!peaks || peaks.length === 0) return;
    ctx.fillStyle = getComputedStyle(canvas).color;
    const mid = height / 2;
    for (let x = 0; x < width; x++) {
      const t0 = (left + x) / zoom;
      const t1 = (left + x + 1) / zoom;
      const b0 = Math.floor((t0 * timing.speed + timing.audio_offset_s) * rate);
      const b1 = Math.max(b0 + 1, Math.ceil((t1 * timing.speed + timing.audio_offset_s) * rate));
      let peak = 0;
      for (let b = Math.max(0, b0); b < Math.min(peaks.length, b1); b++) {
        if (peaks[b]! > peak) peak = peaks[b]!;
      }
      if (peak === 0) continue;
      const h = Math.max(1, (peak / 255) * (height - 4));
      ctx.fillRect(x, mid - h / 2, 1, h);
    }
  }, [peaks, rate, timing, zoom, left, width, height]);

  return (
    <canvas
      ref={ref}
      aria-hidden
      className="pointer-events-none absolute top-0 text-foreground/35"
      style={{ left, width, height }}
    />
  );
}
