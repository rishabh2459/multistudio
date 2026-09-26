/**
 * Serving the static web UI (apps/web/out) under `app://multicam/`.
 *
 * A custom scheme instead of file:// because the Next.js export uses absolute
 * paths (/_next/...) and routes like /project/?id=... that need index.html
 * resolution, and because it gives the page a stable, secure origin for CORS.
 */
import path from 'node:path';

export const APP_SCHEME = 'app';
export const APP_HOST = 'multicam';
export const APP_ORIGIN = `${APP_SCHEME}://${APP_HOST}`;

const MIME: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.txt': 'text/plain; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.webp': 'image/webp',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.map': 'application/json',
};

export function mimeType(file: string): string {
  return MIME[path.extname(file).toLowerCase()] ?? 'application/octet-stream';
}

/**
 * File for a request path, or null (404). Never leaves `root`.
 * `/` and `/project/` -> index.html; `/settings` -> settings/index.html or settings.html.
 */
export function resolveStaticPath(
  root: string,
  pathname: string,
  isFile: (p: string) => boolean,
): string | null {
  let decoded: string;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    return null;
  }
  if (decoded.includes('\0')) return null;
  const base = path.resolve(root);
  const target = path.resolve(base, '.' + path.posix.normalize('/' + decoded));
  if (target !== base && !target.startsWith(base + path.sep)) return null;
  const candidates = decoded.endsWith('/')
    ? [path.join(target, 'index.html')]
    : [target, path.join(target, 'index.html'), `${target}.html`];
  return candidates.find((c) => isFile(c)) ?? null;
}

/** Content-Security-Policy for the UI: its own files + the local engine only. */
export function contentSecurityPolicy(): string {
  const engine = 'http://127.0.0.1:*';
  return [
    "default-src 'self'",
    // The static export inlines small bootstrap scripts.
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    `connect-src 'self' ${engine}`,
    `media-src 'self' blob: ${engine}`,
    "object-src 'none'",
    "base-uri 'none'",
    "frame-ancestors 'none'",
    "form-action 'none'",
  ].join('; ');
}
