/** The "Copy diagnostic report" text: everything support needs, no secrets. */

export interface DiagnosticInput {
  appVersion: string;
  versions: { electron: string; chrome: string; node: string };
  os: { platform: string; release: string; arch: string; cpus: string; memoryGb: number };
  packaged: boolean;
  paths: Record<string, string>;
  engine: {
    status: string;
    url: string | null;
    pid: number | null;
    restarts: number;
    lastExit: string | null;
  };
  systemInfo: unknown;
  logs: Record<string, string>;
  token: string;
  now: Date;
}

export function redact(text: string, secrets: string[]): string {
  return secrets
    .filter((s) => s.length >= 4)
    .reduce((out, secret) => out.split(secret).join('[redacted]'), text);
}

export function buildDiagnosticReport(d: DiagnosticInput): string {
  const lines = [
    '# Multicam Studio diagnostic report',
    `Created: ${d.now.toISOString()}`,
    '',
    '## App',
    `Version: ${d.appVersion}${d.packaged ? '' : ' (development)'}`,
    `Electron ${d.versions.electron} · Chrome ${d.versions.chrome} · Node ${d.versions.node}`,
    `OS: ${d.os.platform} ${d.os.release} (${d.os.arch}) · ${d.os.cpus} · ${d.os.memoryGb.toFixed(1)} GB RAM`,
    '',
    '## Engine',
    `Status: ${d.engine.status}`,
    `URL: ${d.engine.url ?? '-'} · pid ${d.engine.pid ?? '-'}`,
    `Automatic restarts: ${d.engine.restarts}${d.engine.lastExit ? ` · last stop: ${d.engine.lastExit}` : ''}`,
    '',
    '## Paths',
    ...Object.entries(d.paths).map(([k, v]) => `${k}: ${v}`),
    '',
    '## System info (from the engine)',
    typeof d.systemInfo === 'string' ? d.systemInfo : JSON.stringify(d.systemInfo, null, 2),
  ];
  for (const [name, text] of Object.entries(d.logs)) {
    lines.push('', `## ${name} (last lines)`, text || '(empty)');
  }
  return redact(lines.join('\n'), [d.token]) + '\n';
}
