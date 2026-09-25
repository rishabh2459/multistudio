import { makeJob } from '@/test/fixtures';

import { mergeJob, parseJobEvent } from './sse';

describe('job events', () => {
  it('parses job events and ignores anything else', () => {
    const job = makeJob();
    expect(parseJobEvent(JSON.stringify(job))).toEqual(job);
    expect(parseJobEvent('not json')).toBeNull();
    expect(parseJobEvent('{"hello": 1}')).toBeNull();
    expect(parseJobEvent('null')).toBeNull();
  });

  it('merges updates into a newest-first list', () => {
    const older = makeJob({ id: 'a', created_at: '2026-01-01T10:00:00Z' });
    const newer = makeJob({ id: 'b', created_at: '2026-01-01T11:00:00Z' });
    expect(mergeJob(undefined, older)).toEqual([older]);
    expect(mergeJob([older], newer).map((j) => j.id)).toEqual(['b', 'a']);
    const done = { ...older, status: 'succeeded' as const, progress: 1 };
    const merged = mergeJob([newer, older], done);
    expect(merged).toHaveLength(2);
    expect(merged[1]).toEqual(done);
  });
});
