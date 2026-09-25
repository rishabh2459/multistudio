import { mockFetch } from '@/test/fetch';

import { api, ApiError, errorDetail } from './api';
import { resourceUrl } from './config';
import { useSettings } from './settings-store';

describe('api client', () => {
  beforeEach(() => {
    useSettings.getState().reset();
    useSettings.getState().update({ apiUrl: 'http://127.0.0.1:9000/' });
  });
  afterEach(() => vi.unstubAllGlobals());

  it('calls the configured API and sends the token', async () => {
    useSettings.getState().update({ apiToken: 's3cret' });
    const calls = mockFetch({ 'POST /api/projects': { id: 'p' } });
    await api.createProject({ name: 'Ep 1', preset: 'calm' });
    expect(calls[0]).toMatchObject({
      method: 'POST',
      url: 'http://127.0.0.1:9000/api/projects',
      body: { name: 'Ep 1', preset: 'calm' },
    });
    expect(calls[0]!.headers).toMatchObject({ 'X-Multicam-Token': 's3cret' });
  });

  it('turns errors into readable messages', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json({ detail: 'cam2.mp4 is already in this project' }, { status: 409 }),
      ),
    );
    await expect(api.addClip('p', { path: '/x.mp4' })).rejects.toMatchObject({
      status: 409,
      detail: 'cam2.mp4 is already in this project',
    });
    expect(errorDetail({ detail: [{ loc: ['body', 'name'], msg: 'too short' }] }, 'fallback')).toBe(
      'name: too short',
    );
    expect(errorDetail('???', 'fallback')).toBe('fallback');
  });

  it('reports an unreachable engine as status 0', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))),
    );
    const err = await api.health().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(0);
  });

  it('handles 204 and a missing cutlist', async () => {
    mockFetch({ 'DELETE /api/projects/p': null });
    await expect(api.deleteProject('p')).resolves.toBeUndefined();
    expect(await api.getCutlist('p')).toBeNull(); // unmocked -> 404
  });

  it('puts the token in resource URLs (video, event stream)', () => {
    expect(resourceUrl('/api/exports/e/file', { base: 'http://h:1', token: 'a b' })).toBe(
      'http://h:1/api/exports/e/file?token=a+b',
    );
    expect(resourceUrl('/x', { base: 'http://h:1', token: '' })).toBe('http://h:1/x');
  });
});
