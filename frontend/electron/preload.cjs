// Preload — exposes a minimal IPC bridge to the renderer.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('overlord', {
  backendUrl: () => ipcRenderer.invoke('overlord.backendUrl'),
  openExternal: (url) => ipcRenderer.invoke('overlord.openExternal', url),
});
