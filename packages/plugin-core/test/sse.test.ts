import { describe, expect, it } from 'vitest';

import { SseParser } from '../src/events';

describe('SseParser', () => {
  it('parses events split across chunks', () => {
    const p = new SseParser();
    expect(p.push('event: progress\ndata: {"a"')).toEqual([]);
    expect(p.push(':1}\n\n: ping\n\nevent: plan_ready\r\ndata: {"cuts":3}\r\n\r\n')).toEqual([
      { event: 'progress', data: '{"a":1}' },
      { event: 'plan_ready', data: '{"cuts":3}' },
    ]);
  });

  it('joins multi-line data and defaults the event name', () => {
    const p = new SseParser();
    expect(p.push('data: one\ndata: two\n\n')).toEqual([{ event: 'message', data: 'one\ntwo' }]);
  });

  it('keeps a CRLF split across chunks as one line end', () => {
    const p = new SseParser();
    expect(p.push('event: plan_ready\r')).toEqual([]);
    expect(p.push('\ndata: {"cuts":1}\r\n\r')).toEqual([]);
    expect(p.push('\n')).toEqual([{ event: 'plan_ready', data: '{"cuts":1}' }]);
  });
});
