// Electron main process — boots the Python backend and the renderer.
//
// Enhancements over v0:
//   • Detects first-run and surfaces a splash screen while setup runs.
//   • IPC to toggle auto-start at login (Windows / macOS / Linux).
//   • Supports --minimized flag for Windows startup-folder launches.
//   • Kills the backend cleanly on exit (SIGTERM / taskkill).
//   • Single-instance lock — clicking the tray icon re-focuses.
import { app, BrowserWindow, ipcMain, shell, Tray, Menu, nativeImage } from 'electron';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn, execSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const isDev = !app.isPackaged;

const BACKEND_PORT = process.env.OVERLORD_PORT || 8765;
const START_MINIMIZED = process.argv.includes('--minimized');
let backendProc = null;
let mainWindow = null;
let tray = null;

function projectRoot() {
  return path.resolve(__dirname, '..', '..');
}

// ---------------------------------------------------------------------------
// Prerequisite / setup detection
// ---------------------------------------------------------------------------

function isSetupDone() {
  const root = projectRoot();
  const venvBin = process.platform === 'win32'
    ? path.join(root, '.venv', 'Scripts', 'python.exe')
    : path.join(root, '.venv', 'bin', 'python');
  const nodeModules = path.join(root, 'frontend', 'node_modules');
  return fs.existsSync(venvBin) && fs.existsSync(nodeModules);
}

// ---------------------------------------------------------------------------
// Backend lifecycle
// ---------------------------------------------------------------------------

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
  const spawnOpts = {
    cwd: root,
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
    stdio: ['ignore', 'pipe', 'pipe'],
  };
  if (process.platform === 'win32') {
    spawnOpts.windowsHide = true;
  }
  backendProc = spawn(pythonBin, args, spawnOpts);
  backendProc.stdout.on('data', (d) => process.stdout.write(`[backend] ${d}`));
  backendProc.stderr.on('data', (d) => process.stderr.write(`[backend] ${d}`));
  backendProc.on('exit', (code) => {
    process.stderr.write(`[backend] exited with code ${code}\n`);
    backendProc = null;
  });
}

async function waitForBackend(timeoutMs = 20000) {
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

function killBackend() {
  if (!backendProc) return;
  try {
    if (process.platform === 'win32') {
      // On Windows, SIGTERM doesn't work for Python; use taskkill /T to kill
      // the process tree (uvicorn + its workers).
      execSync(`taskkill /pid ${backendProc.pid} /T /F`, { stdio: 'ignore' });
    } else {
      backendProc.kill('SIGTERM');
    }
  } catch { /* ignore */ }
}

// ---------------------------------------------------------------------------
// Window
// ---------------------------------------------------------------------------

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1360,
    height: 860,
    minWidth: 1000,
    minHeight: 700,
    backgroundColor: '#080a13',
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    autoHideMenuBar: true,
    show: !START_MINIMIZED,
    icon: nativeImage.createEmpty(),   // placeholder; override with a real icon in production
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

  mainWindow.on('close', (e) => {
    // Minimize to tray on close if the tray is active
    if (tray && !app.isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });
}

// ---------------------------------------------------------------------------
// Tray
// ---------------------------------------------------------------------------

function createTray() {
  const icon = nativeImage.createEmpty();
  tray = new Tray(icon);
  tray.setToolTip('AI Overlord');
  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Show window',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
      },
    },
    { type: 'separator' },
    {
      label: 'Quit AI Overlord',
      click: () => {
        app.isQuitting = true;
        app.quit();
      },
    },
  ]);
  tray.setContextMenu(contextMenu);
  tray.on('double-click', () => {
    if (mainWindow) { mainWindow.show(); mainWindow.focus(); }
  });
}

// ---------------------------------------------------------------------------
// Auto-start at login
// ---------------------------------------------------------------------------

function autoStartPath() {
  const root = projectRoot();
  if (app.isPackaged) {
    return process.execPath;
  }
  // Dev mode: we start via `Start AI Overlord.bat` or the launcher
  if (process.platform === 'win32') {
    return path.join(root, 'Start AI Overlord.bat');
  } else if (process.platform === 'darwin') {
    return path.join(root, 'Start AI Overlord.command');
  }
  return path.join(root, 'start-ai-overlord.sh');
}

function isAutoStartEnabled() {
  if (process.platform === 'win32') {
    const startupDir = path.join(os.homedir(), 'AppData', 'Roaming',
      'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup');
    return fs.existsSync(path.join(startupDir, 'AI Overlord.lnk'))
        || fs.existsSync(path.join(startupDir, 'AI Overlord.bat'));
  }
  if (process.platform === 'darwin') {
    const plist = path.join(os.homedir(), 'Library', 'LaunchAgents', 'ai.overlord.startup.plist');
    return fs.existsSync(plist);
  }
  // Linux XDG autostart
  const autostart = path.join(
    process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config'),
    'autostart', 'ai-overlord.desktop');
  return fs.existsSync(autostart);
}

function enableAutoStart() {
  const target = autoStartPath();
  if (process.platform === 'win32') {
    const startupDir = path.join(os.homedir(), 'AppData', 'Roaming',
      'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup');
    fs.mkdirSync(startupDir, { recursive: true });
    // Write a .bat that starts the app minimized
    const batContent = `@echo off\r\ncd /d "${projectRoot()}"\r\nstart "" pythonw launch.py --no-electron\r\ntimeout /t 5 >nul\r\nstart "" "${process.execPath}" --minimized\r\n`;
    if (app.isPackaged) {
      // For packaged app, just call the exe
      const shortcutContent = `@echo off\r\nstart "" "${process.execPath}" --minimized\r\n`;
      fs.writeFileSync(path.join(startupDir, 'AI Overlord.bat'), shortcutContent, 'utf-8');
    } else {
      fs.writeFileSync(path.join(startupDir, 'AI Overlord.bat'), batContent, 'utf-8');
    }
    return true;
  }

  if (process.platform === 'darwin') {
    const agentsDir = path.join(os.homedir(), 'Library', 'LaunchAgents');
    fs.mkdirSync(agentsDir, { recursive: true });
    const plist = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>ai.overlord.startup</string>
  <key>ProgramArguments</key>
  <array>
    <string>${target}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <false/>
  <key>WorkingDirectory</key>
  <string>${projectRoot()}</string>
</dict>
</plist>
`;
    fs.writeFileSync(path.join(agentsDir, 'ai.overlord.startup.plist'), plist, 'utf-8');
    return true;
  }

  // Linux XDG autostart
  const configDir = process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config');
  const autostartDir = path.join(configDir, 'autostart');
  fs.mkdirSync(autostartDir, { recursive: true });
  const desktop = `[Desktop Entry]
Type=Application
Name=AI Overlord
Exec=${target}
Terminal=false
X-GNOME-Autostart-enabled=true
Comment=Autonomous AI agent council
`;
  fs.writeFileSync(path.join(autostartDir, 'ai-overlord.desktop'), desktop, 'utf-8');
  return true;
}

function disableAutoStart() {
  if (process.platform === 'win32') {
    const startupDir = path.join(os.homedir(), 'AppData', 'Roaming',
      'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup');
    for (const name of ['AI Overlord.lnk', 'AI Overlord.bat']) {
      const p = path.join(startupDir, name);
      if (fs.existsSync(p)) fs.unlinkSync(p);
    }
    return true;
  }
  if (process.platform === 'darwin') {
    const plist = path.join(os.homedir(), 'Library', 'LaunchAgents', 'ai.overlord.startup.plist');
    if (fs.existsSync(plist)) fs.unlinkSync(plist);
    return true;
  }
  const configDir = process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config');
  const desktop = path.join(configDir, 'autostart', 'ai-overlord.desktop');
  if (fs.existsSync(desktop)) fs.unlinkSync(desktop);
  return true;
}

// ---------------------------------------------------------------------------
// IPC handlers
// ---------------------------------------------------------------------------

function registerIPC() {
  ipcMain.handle('overlord.backendUrl', () => `http://127.0.0.1:${BACKEND_PORT}`);
  ipcMain.handle('overlord.openExternal', (_e, url) => shell.openExternal(url));
  ipcMain.handle('overlord.platform', () => ({
    os: process.platform,
    arch: process.arch,
    version: os.release(),
    isPackaged: app.isPackaged,
    isSetupDone: isSetupDone(),
  }));
  ipcMain.handle('overlord.autoStart.get', () => isAutoStartEnabled());
  ipcMain.handle('overlord.autoStart.set', (_e, enabled) => {
    if (enabled) return enableAutoStart();
    return disableAutoStart();
  });
  ipcMain.handle('overlord.env.keys', () => {
    // Detect any API keys already set in the system environment
    const PREFIX_MAP = {
      MISTRAL_API_KEY: 'mistral',
      NVIDIA_API_KEY: 'nvidia',
      GOOGLE_AI_API_KEY: 'google',
      GROQ_API_KEY: 'groq',
      OPENROUTER_API_KEY: 'openrouter',
      CEREBRAS_API_KEY: 'cerebras',
      TOGETHER_API_KEY: 'together',
    };
    const found = {};
    for (const [envVar, provider] of Object.entries(PREFIX_MAP)) {
      if (process.env[envVar]) {
        found[provider] = envVar;
      }
    }
    return found;
  });
}

// ---------------------------------------------------------------------------
// Single instance lock
// ---------------------------------------------------------------------------

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

app.whenReady().then(async () => {
  registerIPC();
  createTray();
  spawnBackend();
  await waitForBackend();
  createWindow();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.isQuitting = true;
    app.quit();
  }
});

app.on('before-quit', () => {
  app.isQuitting = true;
  killBackend();
});
