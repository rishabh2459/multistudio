import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { contentSecurityPolicy, mimeType, resolveStaticPath } from './static-files';

const root = path.resolve('/srv/web');
const files = new Set(
  ['index.html', 'project/index.html', '404.html', '_next/static/chunks/app.js', 'about.html'].map(
    (f) => path.join(root, f),
  ),
);
const isFile = (p: string) => files.has(p);

describe('resolveStaticPath', () => {
  it('maps routes of the static export to files', () => {
    expect(resolveStaticPath(root, '/', isFile)).toBe(path.join(root, 'index.html'));
    expect(resolveStaticPath(root, '/project/', isFile)).toBe(
      path.join(root, 'project/index.html'),
    );
    expect(resolveStaticPath(root, '/project', isFile)).toBe(path.join(root, 'project/index.html'));
    expect(resolveStaticPath(root, '/about', isFile)).toBe(path.join(root, 'about.html'));
    expect(resolveStaticPath(root, '/_next/static/chunks/app.js', isFile)).toBe(
      path.join(root, '_next/static/chunks/app.js'),
    );
    expect(resolveStaticPath(root, '/missing/', isFile)).toBeNull();
  });

  it('never leaves the web folder', () => {
    expect(resolveStaticPath(root, '/../../etc/passwd', isFile)).toBeNull();
    expect(resolveStaticPath(root, '/%2e%2e/%2e%2e/etc/passwd', isFile)).toBeNull();
    expect(resolveStaticPath(root, '/..%5c..%5cwindows', isFile)).toBeNull();
    expect(resolveStaticPath(root, '/%E0%A4%A', isFile)).toBeNull(); // bad escape
    expect(resolveStaticPath(root, '/index.html%00.js', isFile)).toBeNull();
  });
});

describe('mime types and CSP', () => {
  it('knows the web file types', () => {
    expect(mimeType('a/b.js')).toMatch(/javascript/);
    expect(mimeType('x.HTML')).toMatch(/text\/html/);
    expect(mimeType('font.woff2')).toBe('font/woff2');
    expect(mimeType('blob.bin')).toBe('application/octet-stream');
  });

  it('only allows the local engine besides our own files', () => {
    const csp = contentSecurityPolicy();
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("connect-src 'self' http://127.0.0.1:*");
    expect(csp).toContain("object-src 'none'");
    expect(csp).not.toMatch(/https?:\/\/\*|\*\.com/);
  });
});
