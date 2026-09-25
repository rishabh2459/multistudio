/** Replace fetch with a router: `{ 'GET /api/projects': body }`. */
export function mockFetch(routes: Record<string, unknown>) {
  const calls: Array<{ method: string; url: string; body: unknown; headers: HeadersInit }> = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const method = init.method ?? 'GET';
    const url = new URL(String(input));
    calls.push({
      method,
      url: url.toString(),
      body: init.body ? JSON.parse(String(init.body)) : undefined,
      headers: init.headers ?? {},
    });
    const key = `${method} ${url.pathname}`;
    if (!(key in routes)) {
      return new Response(JSON.stringify({ detail: `no mock for ${key}` }), { status: 404 });
    }
    const body = routes[key];
    return body === null
      ? new Response(null, { status: 204 })
      : new Response(JSON.stringify(body), { status: 200 });
  });
  vi.stubGlobal('fetch', fn);
  return calls;
}
