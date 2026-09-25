/**
 * Live job updates over Server-Sent Events.
 *
 * The API streams a `job` event whenever one of the project's jobs changes. If the
 * stream is not available (old browser, proxy, API restarting) `connected` stays
 * false and the queries fall back to polling.
 */
import { useEffect, useRef, useState } from 'react';

import type { Job } from './api';

/** Parse one `job` event; null for anything that is not a job. */
export function parseJobEvent(data: string): Job | null {
  try {
    const value: unknown = JSON.parse(data);
    if (
      value &&
      typeof value === 'object' &&
      typeof (value as Job).id === 'string' &&
      typeof (value as Job).status === 'string'
    ) {
      return value as Job;
    }
  } catch {
    // ignore malformed events
  }
  return null;
}

/** Insert or replace a job in a newest-first list. */
export function mergeJob(jobs: readonly Job[] | undefined, job: Job): Job[] {
  const rest = (jobs ?? []).filter((j) => j.id !== job.id);
  return [job, ...rest].sort((a, b) => b.created_at.localeCompare(a.created_at));
}

export function useEventSource(
  url: string | null,
  event: string,
  onMessage: (data: string) => void,
): { connected: boolean } {
  const [connected, setConnected] = useState(false);
  const handler = useRef(onMessage);
  useEffect(() => {
    handler.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    if (!url || typeof EventSource === 'undefined') {
      setConnected(false);
      return;
    }
    const source = new EventSource(url);
    const listener = (e: MessageEvent<string>) => handler.current(e.data);
    source.addEventListener(event, listener);
    source.onopen = () => setConnected(true);
    // EventSource reconnects on its own; poll meanwhile.
    source.onerror = () => setConnected(false);
    return () => {
      source.removeEventListener(event, listener);
      source.close();
      setConnected(false);
    };
  }, [url, event]);

  return { connected };
}
