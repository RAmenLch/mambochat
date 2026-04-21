/**
 * Standalone desktop settings window.
 *
 * Opens a separate BrowserWindow with an inline HTML settings page
 * that communicates with the main process via IPC.
 * This page does NOT depend on the Vue app or the backend being available.
 */

import { BrowserWindow, ipcMain, app } from 'electron'
import { join, isAbsolute } from 'path'
import http from 'http'
import { AppConfigManager } from './config'
import { BackendProcessManager } from './backend'
import type { AppConfig } from './config'

let settingsWindow: BrowserWindow | null = null

// ---------------------------------------------------------------------------
// HTML template
// ---------------------------------------------------------------------------

function getSettingsHtml(): string {
  return `data:text/html;charset=utf-8,${encodeURIComponent(`<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MamboChat Desktop Settings</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
    background: #f5f7fa;
    color: #303133;
    line-height: 1.6;
  }
  .header {
    background: #fff;
    padding: 16px 24px;
    border-bottom: 1px solid #e4e7ed;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .header h1 {
    font-size: 18px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .header h1 .dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #409eff;
    display: inline-block;
  }
  .header .subtitle {
    font-size: 12px;
    color: #909399;
  }
  .body {
    max-width: 680px;
    margin: 24px auto;
    padding: 0 20px;
  }
  .card {
    background: #fff;
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 16px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    border: 1px solid #ebeef5;
  }
  .card-title {
    font-size: 14px;
    font-weight: 600;
    color: #303133;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .card-title svg { width: 16px; height: 16px; color: #409eff; }
  .form-group {
    margin-bottom: 16px;
  }
  .form-group:last-child { margin-bottom: 0; }
  .form-label {
    display: block;
    font-size: 13px;
    font-weight: 500;
    color: #606266;
    margin-bottom: 6px;
  }
  .form-hint {
    font-size: 12px;
    color: #909399;
    margin-top: 4px;
  }
  .radio-group {
    display: flex;
    gap: 12px;
  }
  .radio-card {
    flex: 1;
    border: 2px solid #e4e7ed;
    border-radius: 8px;
    padding: 14px;
    cursor: pointer;
    transition: all 0.2s;
    text-align: center;
  }
  .radio-card:hover { border-color: #b3d8ff; }
  .radio-card.active { border-color: #409eff; background: #ecf5ff; }
  .radio-card .icon { font-size: 24px; margin-bottom: 6px; }
  .radio-card .label { font-size: 14px; font-weight: 500; }
  .radio-card .desc { font-size: 11px; color: #909399; margin-top: 4px; }
  input[type="text"], input[type="number"] {
    width: 100%;
    padding: 8px 12px;
    border: 1px solid #dcdfe6;
    border-radius: 4px;
    font-size: 14px;
    color: #303133;
    background: #fff;
    transition: border-color 0.2s;
    outline: none;
  }
  input:focus { border-color: #409eff; }
  .port-range {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .port-range input { width: 100px; }
  .port-range .sep { color: #909399; font-weight: 500; }
  .status-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 16px;
    border-radius: 6px;
    font-size: 13px;
    margin-bottom: 12px;
  }
  .status-bar.running { background: #f0f9eb; color: #67c23a; border: 1px solid #e1f3d8; }
  .status-bar.stopped { background: #f4f4f5; color: #909399; border: 1px solid #e9e9eb; }
  .status-bar.error { background: #fef0f0; color: #f56c6c; border: 1px solid #fde2e2; }
  .status-bar .dot {
    width: 8px; height: 8px; border-radius: 50%;
    flex-shrink: 0;
  }
  .status-bar.running .dot { background: #67c23a; }
  .status-bar.stopped .dot { background: #c0c4cc; }
  .status-bar.error .dot { background: #f56c6c; }
  .status-detail {
    display: flex;
    gap: 20px;
    font-size: 12px;
    color: #909399;
    margin-bottom: 12px;
    padding-left: 4px;
  }
  .btn-row {
    display: flex;
    gap: 8px;
    margin-top: 12px;
  }
  .btn {
    padding: 8px 16px;
    border: none;
    border-radius: 4px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-primary { background: #409eff; color: #fff; }
  .btn-primary:hover:not(:disabled) { background: #66b1ff; }
  .btn-success { background: #67c23a; color: #fff; }
  .btn-success:hover:not(:disabled) { background: #85ce61; }
  .btn-danger { background: #f56c6c; color: #fff; }
  .btn-danger:hover:not(:disabled) { background: #f78989; }
  .btn-default { background: #fff; color: #606266; border: 1px solid #dcdfe6; }
  .btn-default:hover:not(:disabled) { color: #409eff; border-color: #c6e2ff; background: #ecf5ff; }
  .btn-block { width: 100%; justify-content: center; }
  .btn-loading .btn-text::after {
    content: '';
    display: inline-block;
    width: 12px; height: 12px;
    border: 2px solid currentColor;
    border-right-color: transparent;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
    margin-left: 4px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .toast {
    position: fixed;
    top: 16px;
    left: 50%;
    transform: translateX(-50%) translateY(-100px);
    padding: 10px 20px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    z-index: 9999;
    transition: transform 0.3s ease;
    white-space: nowrap;
  }
  .toast.show { transform: translateX(-50%) translateY(0); }
  .toast.success { background: #f0f9eb; color: #67c23a; border: 1px solid #e1f3d8; }
  .toast.error { background: #fef0f0; color: #f56c6c; border: 1px solid #fde2e2; }
  .toast.info { background: #ecf5ff; color: #409eff; border: 1px solid #d9ecff; }
  .section-local, .section-remote { display: none; }
  .section-local.active, .section-remote.active { display: block; }
  .config-path {
    font-size: 11px;
    color: #c0c4cc;
    text-align: center;
    padding: 12px;
  }
</style>
</head>
<body>

<div class="header">
  <div>
    <h1><span class="dot"></span>MamboChat Settings</h1>
    <div class="subtitle">Desktop connection configuration</div>
  </div>
</div>

<div class="body">
  <!-- Mode Selection -->
  <div class="card">
    <div class="card-title">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
      Connection Mode
    </div>
    <div class="radio-group">
      <div class="radio-card active" id="modeLocal" onclick="selectMode('local')">
        <div class="icon">🖥️</div>
        <div class="label">Local</div>
        <div class="desc">Run backend locally</div>
      </div>
      <div class="radio-card" id="modeRemote" onclick="selectMode('remote')">
        <div class="icon">🌐</div>
        <div class="label">Remote</div>
        <div class="desc">Connect to remote server</div>
      </div>
    </div>
  </div>

  <!-- Local Settings -->
  <div class="section-local active" id="sectionLocal">
    <div class="card">
      <div class="card-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
        Local Backend
      </div>
      <div class="form-group">
        <label class="form-label">Host</label>
        <input type="text" id="localHost" value="127.0.0.1">
      </div>
      <div class="form-group">
        <label class="form-label">Port Range</label>
        <div class="port-range">
          <input type="number" id="portStart" value="8000" min="1024" max="65535">
          <span class="sep">—</span>
          <input type="number" id="portEnd" value="8010" min="1024" max="65535">
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">Python Path</label>
        <input type="text" id="pythonPath" value="runtime/.venv/Scripts/python.exe">
        <div class="form-hint">Path to the Python executable. Relative paths are resolved from the app resources directory.</div>
      </div>

      <!-- Backend Status -->
      <div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid #ebeef5;">
        <div class="status-bar stopped" id="statusBar">
          <span class="dot"></span>
          <span id="statusText">Checking...</span>
        </div>
        <div class="status-detail" id="statusDetail" style="display:none;">
          <span>Port: <strong id="detailPort">-</strong></span>
          <span>PID: <strong id="detailPid">-</strong></span>
        </div>
        <div class="btn-row">
          <button class="btn btn-primary" id="btnStart" onclick="startBackend()">▶ Start</button>
          <button class="btn btn-danger" id="btnStop" onclick="stopBackend()" style="display:none;">■ Stop</button>
          <button class="btn btn-default" id="btnRestart" onclick="restartBackend()" style="display:none;">↻ Restart</button>
        </div>
      </div>
    </div>
  </div>

  <!-- Remote Settings -->
  <div class="section-remote" id="sectionRemote">
    <div class="card">
      <div class="card-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
        Remote Server
      </div>
      <div class="form-group">
        <label class="form-label">Server URL</label>
        <input type="text" id="remoteUrl" value="http://127.0.0.1:8000" placeholder="http://your-server:port">
        <div class="form-hint">The base URL of the remote MamboChat backend server.</div>
      </div>
    </div>
  </div>

  <!-- Actions -->
  <div class="card">
    <div class="btn-row">
      <button class="btn btn-success" id="btnTest" onclick="testConnection()">Test Connection</button>
      <button class="btn btn-primary" id="btnSave" onclick="saveConfig()">Save & Apply</button>
    </div>
  </div>

  <div class="config-path" id="configPath"></div>
</div>

<div class="toast" id="toast"></div>

<script>
const api = window.electronAPI;
let currentConfig = null;
let statusCleanup = null;

// --- Toast ---
function showToast(msg, type = 'info', duration = 3000) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast ' + type + ' show';
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), duration);
}

// --- Mode ---
function selectMode(mode) {
  document.getElementById('modeLocal').classList.toggle('active', mode === 'local');
  document.getElementById('modeRemote').classList.toggle('active', mode === 'remote');
  document.getElementById('sectionLocal').classList.toggle('active', mode === 'local');
  document.getElementById('sectionRemote').classList.toggle('active', mode === 'remote');
}

function getMode() {
  return document.getElementById('modeLocal').classList.contains('active') ? 'local' : 'remote';
}

// --- Config ---
function gatherConfig() {
  return {
    mode: getMode(),
    local: {
      pythonPath: document.getElementById('pythonPath').value,
      host: document.getElementById('localHost').value,
      portStart: parseInt(document.getElementById('portStart').value, 10) || 8000,
      portEnd: parseInt(document.getElementById('portEnd').value, 10) || 8010,
    },
    remote: {
      url: document.getElementById('remoteUrl').value.replace(/\\/+$/, ''),
    },
  };
}

function applyConfigToUI(config) {
  currentConfig = config;
  selectMode(config.mode);
  document.getElementById('localHost').value = config.local.host;
  document.getElementById('portStart').value = config.local.portStart;
  document.getElementById('portEnd').value = config.local.portEnd;
  document.getElementById('pythonPath').value = config.local.pythonPath;
  document.getElementById('remoteUrl').value = config.remote.url;
}

async function saveConfig() {
  const config = gatherConfig();
  const btn = document.getElementById('btnSave');
  btn.disabled = true;
  btn.classList.add('btn-loading');
  try {
    const prevMode = currentConfig.mode;
    await api.config.update(config);
    currentConfig = config;

    // Apply mode change: start/stop backend as needed
    if (config.mode === 'local') {
      const status = await api.backend.status();
      if (!status.running) {
        const result = await api.backend.start();
        if (result.success) {
          showToast('Config saved, backend started on port ' + result.port, 'success');
        } else {
          showToast('Config saved, but backend failed: ' + (result.error || 'Unknown'), 'error');
        }
      } else {
        // Restart if local settings changed
        const needsRestart = prevMode !== 'local' ||
          config.local.host !== currentConfig.local.host ||
          config.local.portStart !== currentConfig.local.portStart;
        if (needsRestart) {
          await api.backend.restart();
          showToast('Config saved, backend restarted', 'success');
        } else {
          showToast('Config saved', 'success');
        }
      }
    } else {
      // Remote mode: stop local backend if running
      const status = await api.backend.status();
      if (status.running) {
        await api.backend.stop();
      }
      showToast('Config saved, remote mode active', 'success');
    }

    // Notify main process to update main window
    await api.config.apply(config);
    refreshStatus();
  } catch (e) {
    showToast('Save failed: ' + String(e), 'error');
  } finally {
    btn.disabled = false;
    btn.classList.remove('btn-loading');
  }
}

// --- Backend Control ---
async function startBackend() {
  const btn = document.getElementById('btnStart');
  btn.disabled = true;
  try {
    const result = await api.backend.start();
    if (result.success) {
      showToast('Backend started on port ' + result.port, 'success');
    } else {
      showToast('Failed: ' + (result.error || 'Unknown'), 'error');
    }
    refreshStatus();
  } catch (e) {
    showToast('Error: ' + String(e), 'error');
  } finally {
    btn.disabled = false;
  }
}

async function stopBackend() {
  const btn = document.getElementById('btnStop');
  btn.disabled = true;
  try {
    await api.backend.stop();
    showToast('Backend stopped', 'info');
    refreshStatus();
  } catch (e) {
    showToast('Error: ' + String(e), 'error');
  } finally {
    btn.disabled = false;
  }
}

async function restartBackend() {
  const btn = document.getElementById('btnRestart');
  btn.disabled = true;
  try {
    const result = await api.backend.restart();
    if (result.success) {
      showToast('Backend restarted on port ' + result.port, 'success');
    } else {
      showToast('Failed: ' + (result.error || 'Unknown'), 'error');
    }
    refreshStatus();
  } catch (e) {
    showToast('Error: ' + String(e), 'error');
  } finally {
    btn.disabled = false;
  }
}

// --- Status ---
function refreshStatus() {
  api.backend.status().then(status => updateStatusUI(status)).catch(() => {});
}

function updateStatusUI(status) {
  const bar = document.getElementById('statusBar');
  const text = document.getElementById('statusText');
  const detail = document.getElementById('statusDetail');
  const btnStart = document.getElementById('btnStart');
  const btnStop = document.getElementById('btnStop');
  const btnRestart = document.getElementById('btnRestart');

  bar.className = 'status-bar ' + (status.running ? 'running' : (status.error ? 'error' : 'stopped'));

  if (status.running) {
    text.textContent = 'Backend Running';
    detail.style.display = 'flex';
    document.getElementById('detailPort').textContent = status.port || '-';
    document.getElementById('detailPid').textContent = status.pid || '-';
    btnStart.style.display = 'none';
    btnStop.style.display = '';
    btnRestart.style.display = '';
  } else {
    text.textContent = status.error || 'Backend Stopped';
    detail.style.display = 'none';
    btnStart.style.display = '';
    btnStop.style.display = 'none';
    btnRestart.style.display = 'none';
  }
}

// --- Test Connection ---
async function testConnection() {
  const btn = document.getElementById('btnTest');
  btn.disabled = true;
  btn.classList.add('btn-loading');
  try {
    if (getMode() === 'remote') {
      const url = document.getElementById('remoteUrl').value.replace(/\\/+$/, '');
      const result = await api.testConnection(url);
      if (result.ok) {
        showToast(url + ' Connection successful!', 'success');
      } else {
        showToast(url + ' Connection failed: ' + (result.error || 'HTTP ' + result.status), 'error');
      }
    } else {
      const status = await api.backend.status();
      if (status.running) {
        showToast('Backend is running on port ' + status.port, 'success');
      } else {
        showToast('Backend is not running', 'error');
      }
    }
  } catch (e) {
    console.error('Connection test error:', e);
    showToast('Connection test failed: ' + (e && e.message ? e.message : String(e)), 'error');
  } finally {
    btn.disabled = false;
    btn.classList.remove('btn-loading');
  }
}

// --- Init ---
async function init() {
  try {
    const config = await api.config.get();
    applyConfigToUI(config);

    // Get config path
    const path = await api.config.getPath();
    document.getElementById('configPath').textContent = 'Config: ' + path;

    // Subscribe to backend status changes
    statusCleanup = api.backend.onStatusChange(status => updateStatusUI(status));

    refreshStatus();
  } catch (e) {
    showToast('Failed to load config: ' + String(e), 'error');
  }
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
  if (statusCleanup) statusCleanup();
});

init();
</script>
</body>
</html>`)}`}

// ---------------------------------------------------------------------------
// Window management
// ---------------------------------------------------------------------------

export function openDesktopSettings(): void {
  if (settingsWindow && !settingsWindow.isDestroyed()) {
    settingsWindow.focus()
    return
  }

  settingsWindow = new BrowserWindow({
    width: 520,
    height: 640,
    minWidth: 440,
    minHeight: 500,
    resizable: true,
    title: 'MamboChat Settings',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  settingsWindow.setMenu(null)
  settingsWindow.loadURL(getSettingsHtml())
  settingsWindow.webContents.openDevTools()

  settingsWindow.on('closed', () => {
    settingsWindow = null
  })
}

export function getSettingsWindow(): BrowserWindow | null {
  return settingsWindow
}

export function notifySettingsWindowConfigChanged(config: AppConfig): void {
  if (settingsWindow && !settingsWindow.isDestroyed()) {
    settingsWindow.webContents.send('config:updated', config)
  }
}

// ---------------------------------------------------------------------------
// IPC handlers
// ---------------------------------------------------------------------------

export function setupDesktopSettingsIpc(
  configManager: AppConfigManager,
  getMainWindow: () => BrowserWindow | null
): void {
  ipcMain.handle('desktop-settings:open', () => {
    openDesktopSettings()
  })

  ipcMain.handle('config:getPath', () => {
    return configManager.getConfigPath()
  })

  ipcMain.handle('config:apply', (_event, newConfig: AppConfig) => {
    configManager.save(newConfig)

    // Send config:updated to main window so it can update API URL
    const mainWindow = getMainWindow()
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('config:updated', newConfig)
    }

    return true
  })

  ipcMain.handle('test-remote-connection', (_event, url: string) => {
    return new Promise<{ ok: boolean; status?: number; error?: string }>((resolve) => {
      const cleanUrl = url.replace(/\/+$/, '')
      const req = http.get(cleanUrl + '/api/mcp', { timeout: 15000 }, (res) => {
        res.resume() // drain response body
        res.on('end', () => {
          resolve({ ok: res.statusCode === 200, status: res.statusCode })
        })
      })
      req.on('timeout', () => {
        req.destroy()
        resolve({ ok: false, error: 'Timeout' })
      })
      req.on('error', (err) => {
        resolve({ ok: false, error: err.message })
      })
    })
  })
}
