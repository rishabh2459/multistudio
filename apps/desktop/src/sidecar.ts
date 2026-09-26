/**
 * Runs the Python engine (`multicam-api`) as a child process.
 *
 * - starts it with `--port 0 --watch-stdin`, reads `MULTICAM_API_READY port=N`
 *   from stdout, then waits until `/api/system/health` answers;
 * - restarts it after a crash (limited: see RestartPolicy), on the same port when
 *   possible so the open window keeps working;
 * - stops it by closing its stdin (clean shutdown on every OS), then kills it
 *   after a timeout.
 *
 * No Electron imports here, so it is unit-tested with plain Node.
 */
import { spawn, type ChildProcess } from 'node:child_process';
import { EventEmitter } from 'node:events';
import { createInterface } from 'node:readline';

export interface BackendCommand {
  command: string;
  args: string[];
  cwd?: string;
  env?: Record<string, string>;
}

export interface SidecarInfo {
  port: number;
  baseUrl: string;
  pid: number;
}

export type SidecarStatus = 'stopped' | 'starting' | 'ready' | 'restarting' | 'failed';

export type LogFn = (source: 'stdout' | 'stderr' | 'sidecar', line: string) => void;

const READY = /^MULTICAM_API_READY port=(\d+)\s*$/;

/** Port from the server's ready line, or null for any other line. */
export function parseReadyLine(line: string): number | null {
  const match = READY.exec(line);
  if (!match) return null;
  const port = Number(match[1]);
  return port > 0 && port < 65536 ? port : null;
}

/** At most `maxRestarts` automatic restarts within `windowMs`, with growing delays. */
export class RestartPolicy {
  private readonly times: number[] = [];

  constructor(
    readonly maxRestarts = 3,
    readonly windowMs = 5 * 60_000,
    readonly delaysMs: readonly number[] = [500, 2_000, 5_000],
  ) {}

  /** Delay before the next restart, or null if we should give up. */
  next(now: number): number | null {
    while (this.times.length && now - this.times[0]! > this.windowMs) this.times.shift();
    if (this.times.length >= this.maxRestarts) return null;
    const delay = this.delaysMs[Math.min(this.times.length, this.delaysMs.length - 1)] ?? 0;
    this.times.push(now);
    return delay;
  }

  reset(): void {
    this.times.length = 0;
  }
}

export interface SidecarOptions {
  backend: BackendCommand;
  token: string;
  /** Origin of the UI (added to the API's CORS list). */
  uiOrigin: string;
  log?: LogFn;
  readyTimeoutMs?: number;
  policy?: RestartPolicy;
  /** For tests. */
  fetchImpl?: typeof fetch;
}

export class SidecarError extends Error {
  constructor(
    message: string,
    readonly output: string[] = [],
  ) {
    super(message);
    this.name = 'SidecarError';
  }
}

interface SidecarEvents {
  ready: [SidecarInfo];
  /** Crashed and restarted by itself; `portChanged` means the UI must reload. */
  restarted: [{ info: SidecarInfo; portChanged: boolean }];
  /** Crashed and will not be restarted automatically. */
  failed: [SidecarError];
  status: [SidecarStatus];
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export class Sidecar extends EventEmitter<SidecarEvents> {
  private proc: ChildProcess | null = null;
  private current: SidecarInfo | null = null;
  private stopping = false;
  private lastPort: number | null = null;
  private recent: string[] = [];
  private _status: SidecarStatus = 'stopped';
  private _restarts = 0;
  private _lastExit: string | null = null;
  private readonly policy: RestartPolicy;
  private readonly log: LogFn;

  constructor(private readonly opts: SidecarOptions) {
    super();
    this.policy = opts.policy ?? new RestartPolicy();
    this.log = opts.log ?? (() => undefined);
  }

  get info(): SidecarInfo | null {
    return this.current;
  }
  get status(): SidecarStatus {
    return this._status;
  }
  get restarts(): number {
    return this._restarts;
  }
  get lastExit(): string | null {
    return this._lastExit;
  }
  /** Last lines the server printed (for error messages and diagnostics). */
  get recentOutput(): string[] {
    return [...this.recent];
  }

  private setStatus(status: SidecarStatus): void {
    this._status = status;
    this.emit('status', status);
  }

  /** Start the server and resolve once it answers health checks. */
  async start(): Promise<SidecarInfo> {
    this.stopping = false;
    this.policy.reset();
    this.setStatus('starting');
    try {
      const info = await this.launch(this.lastPort);
      this.setStatus('ready');
      this.emit('ready', info);
      return info;
    } catch (err) {
      this.setStatus('failed');
      throw err;
    }
  }

  private async launch(portHint: number | null): Promise<SidecarInfo> {
    try {
      return await this.spawnOnce(portHint ?? 0);
    } catch (err) {
      if (portHint) {
        // The old port may be taken by now: any free port will do.
        this.log('sidecar', `could not reuse port ${portHint}; trying any free port`);
        return this.spawnOnce(0);
      }
      throw err;
    }
  }

  private spawnOnce(port: number): Promise<SidecarInfo> {
    const { backend, token, uiOrigin } = this.opts;
    const args = [...backend.args, '--port', String(port), '--watch-stdin'];
    this.log('sidecar', `starting: ${backend.command} ${args.join(' ')}`);
    this.recent = [];
    const child = spawn(backend.command, args, {
      cwd: backend.cwd,
      env: {
        ...process.env,
        ...backend.env,
        MULTICAM_API_TOKEN: token,
        MULTICAM_CORS: uiOrigin,
        PYTHONUNBUFFERED: '1',
      },
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    });
    this.proc = child;

    return new Promise<SidecarInfo>((resolve, reject) => {
      let settled = false;
      const fail = (message: string) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        this.killNow(child);
        reject(new SidecarError(message, this.recentOutput));
      };
      const timer = setTimeout(
        () => fail('the engine did not start in time'),
        this.opts.readyTimeoutMs ?? 90_000,
      );

      const remember = (source: 'stdout' | 'stderr', line: string) => {
        this.recent.push(line);
        if (this.recent.length > 60) this.recent.shift();
        this.log(source, line);
      };
      createInterface({ input: child.stdout! }).on('line', (line) => {
        remember('stdout', line);
        const ready = parseReadyLine(line);
        if (ready !== null && !settled) {
          const baseUrl = `http://127.0.0.1:${ready}`;
          this.waitForHealth(baseUrl, () => settled).then(
            () => {
              if (settled) return;
              settled = true;
              clearTimeout(timer);
              this.lastPort = ready;
              this.current = { port: ready, baseUrl, pid: child.pid ?? 0 };
              this.log('sidecar', `ready on ${baseUrl} (pid ${child.pid})`);
              resolve(this.current);
            },
            (err: Error) => fail(err.message),
          );
        }
      });
      createInterface({ input: child.stderr! }).on('line', (line) => remember('stderr', line));

      child.on('error', (err) => fail(`could not run ${backend.command}: ${err.message}`));
      child.on('exit', (code, signal) => {
        this._lastExit = signal ? `signal ${signal}` : `exit code ${code}`;
        this.log('sidecar', `engine stopped (${this._lastExit})`);
        if (this.proc === child) this.proc = null;
        if (!settled) {
          fail(`the engine stopped during startup (${this._lastExit})`);
          return;
        }
        if (!this.stopping) void this.recover();
      });
    });
  }

  private async waitForHealth(baseUrl: string, cancelled: () => boolean): Promise<void> {
    const doFetch = this.opts.fetchImpl ?? fetch;
    const deadline = Date.now() + (this.opts.readyTimeoutMs ?? 90_000);
    while (!cancelled()) {
      try {
        const res = await doFetch(`${baseUrl}/api/system/health`);
        if (res.ok) return;
      } catch {
        // not listening yet (database migrations run at startup)
      }
      if (Date.now() > deadline) throw new Error('the engine does not answer health checks');
      await sleep(150);
    }
  }

  private async recover(): Promise<void> {
    const before = this.current;
    this.current = null;
    const delay = this.policy.next(Date.now());
    if (delay === null) {
      this.setStatus('failed');
      this.emit(
        'failed',
        new SidecarError(`the engine keeps stopping (${this._lastExit})`, this.recentOutput),
      );
      return;
    }
    this.setStatus('restarting');
    this.log('sidecar', `restarting in ${delay} ms`);
    await sleep(delay);
    if (this.stopping) return;
    try {
      const info = await this.launch(before?.port ?? this.lastPort);
      this._restarts += 1;
      this.setStatus('ready');
      this.emit('restarted', { info, portChanged: info.port !== before?.port });
    } catch (err) {
      this.log('sidecar', `restart failed: ${(err as Error).message}`);
      await this.recover();
    }
  }

  /** Stop the server: close stdin (clean shutdown), kill after `timeoutMs`. */
  async stop(timeoutMs = 8_000): Promise<void> {
    this.stopping = true;
    const child = this.proc;
    this.current = null;
    if (!child || child.exitCode !== null || child.signalCode !== null) {
      this.setStatus('stopped');
      return;
    }
    const exited = new Promise<void>((resolve) => child.once('exit', () => resolve()));
    child.stdin?.end();
    const clean = await Promise.race([exited.then(() => true), sleep(timeoutMs).then(() => false)]);
    if (!clean) {
      this.log('sidecar', 'engine did not stop in time; killing it');
      this.killNow(child);
      await Promise.race([exited, sleep(3_000)]);
    }
    this.setStatus('stopped');
  }

  private killNow(child: ChildProcess): void {
    child.stdin?.destroy(); // a surviving grandchild sees EOF on stdin and exits too
    if (child.exitCode !== null || child.signalCode !== null || !child.pid) return;
    if (process.platform === 'win32') {
      // Kill the whole tree (in development `uv run` starts Python as a child).
      spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true });
    } else {
      child.kill('SIGKILL');
    }
  }
}
