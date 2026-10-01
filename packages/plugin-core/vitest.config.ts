import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['test/**/*.test.ts', 'test/**/*.test.tsx'],
    environmentMatchGlobs: [['test/**/*.test.tsx', 'jsdom']],
    testTimeout: 120_000,
  },
});
