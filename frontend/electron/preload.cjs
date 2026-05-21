// Preload — exposes a minimal IPC bridge to the renderer.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('overlord', {
  backendUrl: () => ipcRenderer.invoke('overlord.backendUrl'),
  openExternal: (url) => ipcRenderer.invoke('overlord.openExternal', url),
  platform: () => ipcRenderer.invoke('overlord.platform'),
  autoStart: {
    get: () => ipcRenderer.invoke('overlord.autoStart.get'),
    set: (enabled) => ipcRenderer.invoke('overlord.autoStart.set', enabled),
  },
  envKeys: () => ipcRenderer.invoke('overlord.env.keys'),
});
