import { makeJob } from '@/test/fixtures';

import {
  etaText,
  jobWarnings,
  latestAnalysisJob,
  latestJob,
  speakerTimes,
  stageLabel,
  vadBackend,
} from './jobs';

const auto = makeJob({
  status: 'succeeded',
  result: {
    analyze: {
      vad_backend: 'silero',
      speakers: [
        { clip_id: 'a', label: 'Host', speaking_s: 120.5 },
        { clip_id: 'b', label: 'Guest', speaking_s: 80 },
      ],
    },
    warnings: ['cam2.mp4: low sync confidence', 42],
  },
});

describe('job helpers', () => {
  it('labels stages for people', () => {
    expect(stageLabel(makeJob({ stage: 'analyze' }))).toBe('Detecting speakers');
    expect(stageLabel(makeJob({ stage: 'render:video' }))).toBe('Rendering video');
    expect(stageLabel(makeJob({ status: 'queued', stage: '' }))).toBe('Waiting');
    expect(stageLabel(makeJob({ stage: 'something-new' }))).toBe('something-new');
  });

  it('reads speaker times and warnings defensively', () => {
    expect(speakerTimes(auto)).toEqual([
      { clipId: 'a', label: 'Host', speakingS: 120.5 },
      { clipId: 'b', label: 'Guest', speakingS: 80 },
    ]);
    expect(vadBackend(auto)).toBe('silero');
    expect(jobWarnings(auto)).toEqual(['cam2.mp4: low sync confidence']);
    expect(speakerTimes(makeJob({ kind: 'render', result: { speakers: [] } }))).toEqual([]);
    expect(speakerTimes(makeJob({ result: { analyze: 'oops' } }))).toEqual([]);
    expect(speakerTimes(undefined)).toEqual([]);
  });

  it('finds the latest jobs (newest first)', () => {
    const render = makeJob({ id: 'r', kind: 'render' });
    const jobs = [render, auto];
    expect(latestJob(jobs, ['auto', 'decide'])).toBe(auto);
    expect(latestJob(jobs, ['render'])).toBe(render);
    expect(latestAnalysisJob(jobs)).toBe(auto);
  });

  it('turns the render message into a friendly ETA', () => {
    expect(etaText('120/900 frames, ETA 42 s')).toBe('about 42 s left');
    expect(etaText('120/900 frames, ETA 600 s')).toBe('about 10 min left');
    expect(etaText('120/900 frames')).toBeNull();
  });
});
