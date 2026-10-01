// jsdom ships no types and @types/jsdom is not a dependency: only JSDOM is used.
declare module 'jsdom' {
  export class JSDOM {
    constructor(html?: string, options?: { url?: string });
    readonly window: Window & typeof globalThis;
  }
}
