import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { makeClip, makeJob, makeProject } from '@/test/fixtures';
import { mockFetch } from '@/test/fetch';
import { renderWithClient } from '@/test/render';
import { useSettings } from '@/lib/settings-store';

import { NewProjectForm } from './new-project-form';
import { parsePaths } from './project/clip-setup';
import { JobProgress } from './project/job-progress';
import { SyncTable } from './project/processing-panel';
import { outputPath } from './project/result-panel';
import { initialStep, Stepper } from './project/stepper';
import { ProjectList } from './project-list';

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

beforeEach(() => {
  useSettings.getState().reset();
  useSettings.getState().update({ apiUrl: 'http://api.test' });
  push.mockReset();
});
afterEach(() => vi.unstubAllGlobals());

describe('stepper', () => {
  it('starts where the project is', () => {
    expect(initialStep(0, false)).toBe('setup');
    expect(initialStep(3, false)).toBe('process');
    expect(initialStep(3, true)).toBe('result');
  });

  it('disables steps that are not reachable yet', () => {
    const onSelect = vi.fn();
    render(
      <Stepper
        current="setup"
        onSelect={onSelect}
        steps={[
          { id: 'setup', label: 'Cameras', done: false, enabled: true },
          { id: 'process', label: 'Auto edit', done: false, enabled: false },
        ]}
      />,
    );
    expect(screen.getByRole('button', { name: /Cameras/ })).toHaveAttribute('aria-current', 'step');
    expect(screen.getByRole('button', { name: /Auto edit/ })).toBeDisabled();
  });
});

describe('clip setup helpers', () => {
  it('parses pasted paths', () => {
    expect(parsePaths(' "/a b/cam1.mp4"\n\n/c/cam2.mov \r\n')).toEqual([
      '/a b/cam1.mp4',
      '/c/cam2.mov',
    ]);
  });

  it('builds the render output path only when a folder is set', () => {
    expect(outputPath('', 'Ep 1', 'draft')).toBeUndefined();
    expect(outputPath('/Videos/', 'Ep 1', 'draft')).toBe('/Videos/Ep-1-draft.mp4');
  });
});

describe('SyncTable', () => {
  it('flags cameras with low sync confidence', () => {
    const sync = (confidence: number, offset: number) => ({
      reference_clip_id: 'a',
      offset_samples: offset,
      sample_rate: 8000,
      drift_ppm: 1.5,
      confidence,
    });
    const project = makeProject({
      clips: [
        makeClip({ id: 'a', speaker_label: 'Host', sync: sync(1, 0), is_reference: true }),
        makeClip({ id: 'b', speaker_label: 'Guest', sync: sync(0.92, 8000) }),
        makeClip({ id: 'c', speaker_label: 'Other', sync: sync(0.2, -4000) }),
      ],
    });
    render(<SyncTable project={project} />);
    expect(screen.getByText('reference')).toBeInTheDocument();
    expect(screen.getByText('+1000.0 ms')).toBeInTheDocument();
    expect(screen.getByText('−500.0 ms')).toBeInTheDocument();
    expect(screen.getByText('92%')).toBeInTheDocument();
    expect(screen.getByText(/20% – check/)).toBeInTheDocument();
  });
});

describe('JobProgress', () => {
  it('shows progress and cancels a running job', async () => {
    const calls = mockFetch({
      'POST /api/jobs/job-1/cancel': makeJob({ status: 'cancelled' }),
    });
    renderWithClient(<JobProgress job={makeJob({ stage: 'analyze', progress: 0.5 })} />);
    expect(screen.getByText(/Detecting speakers · 50%/)).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '50');
    fireEvent.click(screen.getByRole('button', { name: /Cancel/ }));
    await waitFor(() => expect(calls.map((c) => c.method)).toEqual(['POST']));
  });

  it('shows the error and offers a retry when it failed', () => {
    renderWithClient(
      <JobProgress
        job={makeJob({ status: 'failed', error: 'cam2.mp4: file not found; relink it' })}
      />,
    );
    expect(screen.getByText(/relink it/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Try again/ })).toBeEnabled();
  });

  it('shows nothing once the job succeeded', () => {
    const { container } = renderWithClient(<JobProgress job={makeJob({ status: 'succeeded' })} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('ProjectList', () => {
  it('shows the empty state', async () => {
    mockFetch({ 'GET /api/projects': [] });
    renderWithClient(<ProjectList />);
    expect(await screen.findByText('No projects yet')).toBeInTheDocument();
  });

  it('lists projects and deletes after confirming', async () => {
    const calls = mockFetch({
      'GET /api/projects': [
        {
          id: 'p1',
          name: 'Episode 1',
          preset: 'balanced',
          clip_count: 3,
          cutlist_version: 1,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      'DELETE /api/projects/p1': null,
    });
    renderWithClient(<ProjectList />);
    expect(await screen.findByText('Episode 1')).toBeInTheDocument();
    expect(screen.getByText('3 cameras')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Delete Episode 1' }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true));
  });

  it('explains how to start the engine when it is offline', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Promise.reject(new TypeError('offline'))),
    );
    renderWithClient(<ProjectList />);
    expect(await screen.findByText('The engine is not running')).toBeInTheDocument();
  });
});

describe('NewProjectForm', () => {
  it('creates a project and opens it', async () => {
    const calls = mockFetch({ 'POST /api/projects': makeProject({ id: 'new-id' }) });
    renderWithClient(<NewProjectForm />);
    const create = screen.getByRole('button', { name: 'Create project' });
    expect(create).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: ' Ep 7 ' } });
    fireEvent.change(screen.getByLabelText('Editing style'), { target: { value: 'dynamic' } });
    fireEvent.click(create);
    await waitFor(() => expect(push).toHaveBeenCalledWith('/project/?id=new-id'));
    expect(calls[0]!.body).toEqual({ name: 'Ep 7', preset: 'dynamic' });
  });
});
