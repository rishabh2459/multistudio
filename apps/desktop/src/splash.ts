/** Tiny page shown while the engine starts (a data: URL, no files needed). */
export function splashUrl(dark: boolean): string {
  const bg = dark ? '#111318' : '#f7f7f8';
  const fg = dark ? '#e8e8ea' : '#1b1c1f';
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>Multicam Studio</title>
<style>html,body{height:100%;margin:0;background:${bg};color:${fg};font:15px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
body{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px}
.s{width:28px;height:28px;border:3px solid ${fg}33;border-top-color:${fg};border-radius:50%;animation:r 0.9s linear infinite}
@keyframes r{to{transform:rotate(360deg)}}</style></head>
<body><div class="s"></div><div>Starting the engine…</div></body></html>`;
  return `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
}
