import type { NextConfig } from 'next';

// Static export: the UI is plain HTML/JS/CSS files served by the desktop app
// (Phase 6). No Node server, no API routes: all logic lives in the Python API.
const config: NextConfig = {
  output: 'export',
  trailingSlash: true, // /project/ -> project/index.html (works from a file server)
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default config;
