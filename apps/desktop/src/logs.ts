/** Plain-text log files in the OS log folder, rotated at startup. */
import fs from 'node:fs';
import path from 'node:path';

export const MAX_LOG_BYTES = 5 * 1024 * 1024;

export class LogFile {
  private readonly fd: number;

  constructor(
    readonly file: string,
    maxBytes = MAX_LOG_BYTES,
  ) {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    try {
      if (fs.statSync(file).size > maxBytes) fs.renameSync(file, `${file}.1`);
    } catch {
      // no log yet
    }
    this.fd = fs.openSync(file, 'a');
  }

  write(source: string, line: string): void {
    try {
      fs.writeSync(this.fd, `${new Date().toISOString()} [${source}] ${line}\n`);
    } catch {
      // logging must never crash the app
    }
  }

  close(): void {
    try {
      fs.closeSync(this.fd);
    } catch {
      // already closed
    }
  }
}

/** Last `lines` lines of a text file ('' if it does not exist). */
export function tailFile(file: string, lines: number, maxBytes = 256 * 1024): string {
  try {
    const size = fs.statSync(file).size;
    const length = Math.min(size, maxBytes);
    const buffer = Buffer.alloc(length);
    const fd = fs.openSync(file, 'r');
    try {
      fs.readSync(fd, buffer, 0, length, size - length);
    } finally {
      fs.closeSync(fd);
    }
    return buffer.toString('utf8').split(/\r?\n/).filter(Boolean).slice(-lines).join('\n');
  } catch {
    return '';
  }
}
