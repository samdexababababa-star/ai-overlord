// Electron main process — boots the Python backend and the renderer.
import { app, BrowserWindow, ipcMain, shell } from 'electron';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import fs from 'node:fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const isDev = !app.isPackaged;

const BACKEND_PORT = process.env.OVERLORD_PORT || 8765;
let backendProc = null;
let mainWindow = null;

function projectRoot() {
  return path.resolve(__dirname, '..', '..');
}

function spawnBackend() {
  if (process.env.OVERLORD_NO_BACKEND === '1') return;
  const root = projectRoot();
  const venvPython = process.platform === 'win32'
    ? path.join(root, '.venv', 'Scripts', 'python.exe')
    : path.join(root, '.venv', 'bin', 'python');
  const pythonBin = fs.existsSync(venvPython) ? venvPython : 'python3';
  const args = ['-m', 'uvicorn', 'backend.app.main:app',
    '--host', '127.0.0.1',
    '--port', String(BACKEND_PORT),
    '--log-level', 'info'];
  backendProc = spawn(pythonBin, args, {
    cwd: root,
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  backendProc.stdout.on('data', (d) => process.stdout.write(`[backend] ${d}`));
  backendProc.stderr.on('data', (d) => process.stderr.write(`[backend] ${d}`));
  backendProc.on('exit', (code) => {
    process.stderr.write(`[backend] exited with code ${code}\n`);
  });
}

async function waitForBackend(timeoutMs = 15000) {
  const url = `http://127.0.0.1:${BACKEND_PORT}/health`;
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await fetch(url);
      if (r.ok) return true;
    } catch {
      /* keep trying */
    }
    await new Promise((res) => setTimeout(res, 300));
  }
  return false;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 1000,
    minHeight: 700,
    backgroundColor: '#080a13',
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
}

app.whenReady().then(async () => {
  spawnBackend();
  await waitForBackend();
  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  if (backendProc) {
    try { backendProc.kill('SIGTERM'); } catch { /* ignore */ }
  }
});

ipcMain.handle('overlord.backendUrl', () => `http://127.0.0.1:${BACKEND_PORT}`);
ipcMain.handle('overlord.openExternal', (_e, url) => shell.openExternal(url));
