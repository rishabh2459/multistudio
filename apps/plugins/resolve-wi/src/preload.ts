import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('multicam', {
  invoke: (target: string, method: string, args: unknown[]) =>
    ipcRenderer.invoke('multicam', target, method, args),
});
