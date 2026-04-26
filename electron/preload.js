const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  isElectron: true,
  getVersion: () => ipcRenderer.invoke("get-version"),
  getBackendUrl: () => ipcRenderer.invoke("get-backend-url"),
});
