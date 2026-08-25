/**
 * Standalone desktop settings window.
 *
 * Opens a separate BrowserWindow with an inline HTML settings page
 * that communicates with the main process via IPC.
 * This page does NOT depend on the Vue app or the backend being available.
 */

import { BrowserWindow, ipcMain } from 'electron'
import { join } from 'path'
import http from 'http'
import os from 'os'
import { AppConfigManager } from './config'
import type { AppConfig } from './config'
import { getDesktopLocale, translate, translations } from './i18n'
import log from './log'

let settingsWindow: BrowserWindow | null = null

// ---------------------------------------------------------------------------
// HTML template
// ---------------------------------------------------------------------------

function getSettingsHtml(): string {
  const locale = getDesktopLocale()
  return `data:text/html;charset=utf-8,${encodeURIComponent(`<!DOCTYPE html>
<html lang="${locale}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${translate(locale, 'settings.title')}</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
    background: #f5f7fa;
    color: #303133;
    line-height: 1.6;
    display: flex;
    flex-direction: column;
  }
  .titlebar {
    height: 36px;
    display: flex;
    align-items: center;
    background: #fff;
    border-bottom: 1px solid #e4e7ed;
    padding-left: 12px;
    -webkit-app-region: drag;
    user-select: none;
    flex-shrink: 0;
  }
  .titlebar-title {
    font-size: 12px;
    font-weight: 600;
    color: #303133;
    letter-spacing: -0.3px;
  }
  .titlebar-spacer { flex: 1; }
  .titlebar-actions {
    -webkit-app-region: no-drag;
    display: flex;
    align-items: center;
    gap: 2px;
    margin-right: 6px;
  }
  .tb-btn {
    width: 30px; height: 30px;
    border: none;
    background: transparent;
    cursor: pointer;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #606266;
    font-size: 15px;
    transition: all 0.15s;
  }
  .tb-btn:hover { background: rgba(0,0,0,0.06); color: #303133; }
  .tb-btn-close:hover { background: #e81123 !important; color: #fff !important; }
  .body {
    max-width: 680px;
    margin: 24px auto;
    padding: 0 20px;
    overflow-y: auto;
    flex: 1;
    min-height: 0;
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
  .status-bar.starting { background: #ecf5ff; color: #409eff; border: 1px solid #d9ecff; }
  .status-bar .dot {
    width: 8px; height: 8px; border-radius: 50%;
    flex-shrink: 0;
  }
  .status-bar.running .dot { background: #67c23a; }
  .status-bar.stopped .dot { background: #c0c4cc; }
  .status-bar.error .dot { background: #f56c6c; }
  .status-bar.starting .dot {
    background: #409eff;
    animation: pulse-dot 1s ease-in-out infinite;
  }
  @keyframes pulse-dot {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(0.8); }
  }
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
  .btn-sm { padding: 4px 10px; font-size: 12px; }
  .api-client-card {
    border: 1px solid #ebeef5;
    border-radius: 6px;
    padding: 14px;
    margin-bottom: 12px;
    background: #fafbfc;
  }
  .api-client-card:last-child { margin-bottom: 0; }
  .api-client-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
  }
  .api-client-header .api-client-title {
    font-size: 13px;
    font-weight: 600;
    color: #303133;
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .api-client-empty {
    text-align: center;
    color: #909399;
    font-size: 13px;
    padding: 20px 0;
    border: 1px dashed #dcdfe6;
    border-radius: 6px;
  }
  .api-client-id {
    font-size: 12px;
    color: #909399;
    margin-bottom: 10px;
    word-break: break-all;
  }
  .api-client-id.registered { color: #67c23a; }
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
  .switch-label {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 13px;
    font-weight: 500;
    color: #303133;
    cursor: pointer;
  }
  .switch {
    position: relative;
    display: inline-block;
    width: 36px;
    height: 20px;
    flex-shrink: 0;
  }
  .switch input { opacity: 0; width: 0; height: 0; }
  .switch-slider {
    position: absolute;
    inset: 0;
    background: #c0c4cc;
    border-radius: 10px;
    transition: all 0.3s;
    cursor: pointer;
  }
  .switch-slider::before {
    content: '';
    position: absolute;
    height: 16px;
    width: 16px;
    left: 2px;
    bottom: 2px;
    background: #fff;
    border-radius: 50%;
    transition: all 0.3s;
  }
  .switch input:checked + .switch-slider { background: #409eff; }
  .switch input:checked + .switch-slider::before { transform: translateX(16px); }
  .network-info {
    margin-top: 12px;
    padding: 12px;
    background: #f4f4f5;
    border-radius: 6px;
    border: 1px solid #e9e9eb;
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  }
  .network-info-title {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 12px;
    font-weight: 600;
    color: #606266;
    margin-bottom: 8px;
  }
  .network-url-line {
    font-size: 12px;
    color: #909399;
    padding: 2px 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .network-url-line .prefix { color: #67c23a; }
  .network-url-line .url { color: #409eff; }
  .current-mode-badge {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    background: #ecf5ff;
    color: #409eff;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    margin-bottom: 16px;
    border: 1px solid #d9ecff;
    transition: all 0.3s;
  }
  .current-mode-badge.remote {
    background: #fdf6ec;
    color: #e6a23c;
    border-color: #faecd8;
  }
  .current-mode-badge .mode-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #409eff;
    flex-shrink: 0;
  }
  .current-mode-badge.remote .mode-dot {
    background: #e6a23c;
  }
  .current-mode-badge .mode-label {
    color: #606266;
  }
  .current-mode-badge .mode-value {
    font-weight: 600;
  }
</style>
</head>
<body>

<!-- Custom title bar -->
<div class="titlebar">
  <span class="titlebar-title">${translate(locale, 'settings.title')}</span>
  <div class="titlebar-spacer"></div>
  <div class="titlebar-actions">
    <button class="tb-btn" id="tbMinimize" title="${translate(locale, 'titlebar.minimize')}">
      <svg width="10" height="1" viewBox="0 0 10 1"><rect width="10" height="1" fill="currentColor"/></svg>
    </button>
    <button class="tb-btn" id="tbMaximize" title="${translate(locale, 'titlebar.maximize')}">
      <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.2">
        <rect x="0.6" y="0.6" width="8.8" height="8.8" rx="1"/>
      </svg>
    </button>
    <button class="tb-btn tb-btn-close" id="tbClose" title="${translate(locale, 'titlebar.close')}">
      <svg width="10" height="10" viewBox="0 0 10 10" stroke="currentColor" stroke-width="1.3" stroke-linecap="round">
        <line x1="0.5" y1="0.5" x2="9.5" y2="9.5"/><line x1="9.5" y1="0.5" x2="0.5" y2="9.5"/>
      </svg>
    </button>
  </div>
</div>

<div class="body">
  <!-- Current Mode Badge -->
  <div class="current-mode-badge" id="activeModeBadge">
    <span class="mode-dot"></span>
    <span class="mode-label">${translate(locale, 'mode.current')}:</span>
    <span class="mode-value" id="activeModeValue">${translate(locale, 'mode.current.local')}</span>
  </div>

  <!-- Mode Selection -->
  <div class="card">
    <div class="card-title">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
      ${translate(locale, 'mode.title')}
    </div>
    <div class="radio-group">
      <div class="radio-card active" id="modeLocal" onclick="selectMode('local')">
        <div class="icon">🖥️</div>
        <div class="label">${translate(locale, 'mode.local')}</div>
        <div class="desc">${translate(locale, 'mode.local.desc')}</div>
      </div>
      <div class="radio-card" id="modeRemote" onclick="selectMode('remote')">
        <div class="icon">🌐</div>
        <div class="label">${translate(locale, 'mode.remote')}</div>
        <div class="desc">${translate(locale, 'mode.remote.desc')}</div>
      </div>
    </div>
    <div class="btn-row" style="margin-top: 16px;">
      <button class="btn btn-success" id="btnTest" onclick="testConnection()">${translate(locale, 'mode.test')}</button>
      <button class="btn btn-primary" id="btnSave" onclick="saveConfig()">${translate(locale, 'mode.save')}</button>
    </div>
  </div>

  <!-- Local Settings -->
  <div class="section-local active" id="sectionLocal">
    <div class="card">
      <div class="card-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
        ${translate(locale, 'local.title')}
      </div>
      <div class="form-group">
        <label class="form-label">${translate(locale, 'local.host')}</label>
        <input type="text" id="localHost" value="127.0.0.1">
      </div>
      <div class="form-group">
        <label class="form-label">${translate(locale, 'local.portRange')}</label>
        <div class="port-range">
          <input type="number" id="portStart" value="8000" min="1024" max="65535">
          <span class="sep">—</span>
          <input type="number" id="portEnd" value="8010" min="1024" max="65535">
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">${translate(locale, 'local.pythonPath')}</label>
        <input type="text" id="pythonPath" value="runtime/python/python.exe">
        <div class="form-hint">${translate(locale, 'local.pythonPath.hint')}</div>
      </div>

      <!-- External Access -->
      <div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid #ebeef5;">
        <label class="switch-label">
          <span class="switch">
            <input type="checkbox" id="allowExternal" onchange="toggleExternalAccess()">
            <span class="switch-slider"></span>
          </span>
          <span>${translate(locale, 'local.externalAccess')}</span>
        </label>
        <div class="form-hint" style="margin-top: 4px; margin-bottom: 0;">${translate(locale, 'local.externalAccess.hint')}</div>
        <div class="form-group" style="margin-top: 12px;">
          <label class="form-label">${translate(locale, 'local.gatewayPort')}</label>
          <input type="number" id="gatewayPort" value="5173" min="1024" max="65535" style="width: 120px;">
          <div class="form-hint">${translate(locale, 'local.gatewayPort.hint')}</div>
        </div>
        <div id="networkInfo" class="network-info" style="display:none;">
          <div class="network-info-title">${translate(locale, 'local.networkUrls')}</div>
          <div id="networkUrls"></div>
        </div>
      </div>

      <!-- Backend Status -->
      <div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid #ebeef5;">
        <div class="status-bar stopped" id="statusBar">
          <span class="dot"></span>
          <span id="statusText">${translate(locale, 'backend.checking')}</span>
        </div>
        <div class="status-detail" id="statusDetail" style="display:none;">
          <span>${translate(locale, 'status.port')}: <strong id="detailPort">-</strong></span>
          <span>${translate(locale, 'status.pid')}: <strong id="detailPid">-</strong></span>
        </div>
        <div class="btn-row">
          <button class="btn btn-primary" id="btnStart" onclick="startBackend()">&#9654; ${translate(locale, 'backend.start')}</button>
          <button class="btn btn-danger" id="btnStop" onclick="stopBackend()" style="display:none;">&#9632; ${translate(locale, 'backend.stop')}</button>
          <button class="btn btn-default" id="btnRestart" onclick="restartBackend()" style="display:none;">&#8635; ${translate(locale, 'backend.restart')}</button>
        </div>
      </div>
    </div>
  </div>

  <!-- Remote Settings -->
  <div class="section-remote" id="sectionRemote">
    <div class="card">
      <div class="card-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
        ${translate(locale, 'remote.title')}
      </div>
      <div class="form-group">
        <label class="form-label">${translate(locale, 'remote.serverUrl')}</label>
        <input type="text" id="remoteUrl" value="http://127.0.0.1:8000" placeholder="http://your-server:port">
        <div class="form-hint">${translate(locale, 'remote.serverUrl.hint')}</div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
        ${translate(locale, 'apiClient.title')}
        <button class="btn btn-success btn-sm" id="btnApiClientAdd" onclick="addApiClientCard()" style="margin-left:auto;">+ ${translate(locale, 'apiClient.add')}</button>
      </div>
      <div id="apiClientList"></div>
    </div>
  </div>


  <div class="config-path" id="configPath"></div>
</div>

<div class="toast" id="toast"></div>

<script>
const T = ${JSON.stringify(translations[locale])};
let currentConfig = null;
let activeMode = 'local';
let statusCleanup = null;

function t(key, params) {
  let text = T[key] || key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      text = text.replace('{' + k + '}', v);
    }
  }
  return text;
}

// --- Active mode badge ---
function updateActiveModeBadge(mode) {
  activeMode = mode;
  const badge = document.getElementById('activeModeBadge');
  const value = document.getElementById('activeModeValue');
  badge.classList.toggle('remote', mode === 'remote');
  value.textContent = mode === 'local' ? t('mode.current.local') : t('mode.current.remote');
}

// --- Title bar buttons ---
const api = window.electronAPI;
document.getElementById('tbMinimize').addEventListener('click', () => api.win.minimize());
document.getElementById('tbMaximize').addEventListener('click', () => api.win.toggleMaximize());
document.getElementById('tbClose').addEventListener('click', () => api.win.close());

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
function collectApiClientsFromDom() {
  const cards = document.querySelectorAll('.api-client-card');
  const clients = [];
  cards.forEach((card, i) => {
    const existing = (currentConfig?.remote?.apiClients && currentConfig.remote.apiClients[i]) || {};
    clients.push({
      name: document.getElementById('apiClientName_' + i)?.value || '',
      backendId: existing.backendId || '',
      apiKey: existing.apiKey || '',
      rootDir: document.getElementById('apiClientRootDir_' + i)?.value || '',
      autoStart: !!(document.getElementById('apiClientAutoStart_' + i)?.checked),
    });
  });
  return clients;
}

function gatherConfig() {
  return {
    mode: getMode(),
    local: {
      pythonPath: document.getElementById('pythonPath').value,
      host: document.getElementById('localHost').value,
      portStart: parseInt(document.getElementById('portStart').value, 10) || 8000,
      portEnd: parseInt(document.getElementById('portEnd').value, 10) || 8010,
      allowExternalAccess: document.getElementById('allowExternal').checked,
      gatewayPort: parseInt(document.getElementById('gatewayPort').value, 10) || 5173,
    },
    remote: {
      url: document.getElementById('remoteUrl').value.replace(/\\/+$/, ''),
      apiClients: collectApiClientsFromDom(),
    },
  };
}

function applyConfigToUI(config) {
  currentConfig = config;
  updateActiveModeBadge(config.mode);
  selectMode(config.mode);
  document.getElementById('localHost').value = config.local.host;
  document.getElementById('portStart').value = config.local.portStart;
  document.getElementById('portEnd').value = config.local.portEnd;
  document.getElementById('pythonPath').value = config.local.pythonPath;
  document.getElementById('allowExternal').checked = !!config.local.allowExternalAccess;
  document.getElementById('gatewayPort').value = config.local.gatewayPort || 5173;
  document.getElementById('remoteUrl').value = config.remote.url;
  renderApiClientCards();
  updateNetworkVisibility();
}

async function saveConfig() {
  const config = gatherConfig();
  const btn = document.getElementById('btnSave');
  btn.disabled = true;
  btn.classList.add('btn-loading');
  try {
    const prevConfig = currentConfig;
    const prevMode = prevConfig.mode;
    await api.config.update(config);
    currentConfig = config;

    // Apply mode change: start/stop backend as needed
    if (config.mode === 'local') {
      const externalChanged = config.local.allowExternalAccess !== prevConfig.local.allowExternalAccess;
      const gatewayPortChanged = config.local.gatewayPort !== (prevConfig.local.gatewayPort || 5173);
      const backendChanged = prevMode !== 'local' ||
        config.local.host !== prevConfig.local.host ||
        config.local.portStart !== prevConfig.local.portStart ||
        config.local.portEnd !== prevConfig.local.portEnd ||
        config.local.pythonPath !== prevConfig.local.pythonPath;

      // Restart gateway if external access or gateway port changed
      if (externalChanged || gatewayPortChanged) {
        const host = config.local.allowExternalAccess ? '0.0.0.0' : '127.0.0.1';
        try {
          const result = await api.gateway.restart(host, config.local.gatewayPort || 5173);
          if (!result.success) {
            showToast(t('toast.gatewayRestartFailed') + ': ' + (result.error || 'Unknown'), 'error');
          }
        } catch (e) { log.error('Gateway restart failed:', e); }
      }

      // Restart backend if backend settings changed or switching from remote
      if (backendChanged) {
        await api.backend.restart();
      }

      if (externalChanged || gatewayPortChanged || backendChanged) {
        showToast(t('toast.savedAndApplied'), 'success');
      } else {
        showToast(t('toast.saved'), 'success');
      }
    } else {
      // Remote mode: stop local backend if running, set gateway to localhost
      const backendStatus = await api.backend.status();
      if (backendStatus.running) {
        await api.backend.stop();
      }
      // Switch gateway to localhost-only and proxy to remote
      const gatewayPort = config.local.gatewayPort || 5173;
      try {
        await api.gateway.restart('127.0.0.1', gatewayPort);
      } catch (e) { log.error('Gateway restart failed:', e); }

      // Handle API clients: when the client list changed (or switching to
      // remote), stop everything and start the auto-start set.
      const clientSig = (list) => (list || [])
        .map(c => (c.backendId || '') + '|' + (c.rootDir || '') + '|' + (c.autoStart ? 1 : 0))
        .join(';');
      const clientsChanged = prevMode !== 'remote' ||
        clientSig(config.remote.apiClients) !== clientSig(prevConfig.remote.apiClients);

      if (clientsChanged) {
        // Stop previous clients first (if running), then start the auto-start ones
        try { await api.apibackend.stop(); } catch (e) { /* ignore */ }
        const autoStartClients = (config.remote.apiClients || []).filter(c => c.autoStart && c.backendId && c.apiKey);
        if (autoStartClients.length > 0) {
          const result = await api.apibackend.start();
          if (result.success) {
            showToast(t('toast.remoteActive') + ' - ' + t('apiClient.status.connected'), 'success');
          } else {
            showToast(t('toast.remoteActive') + ' - ' + t('apiClient.status.error') + ': ' + (result.error || ''), 'warning');
          }
        } else {
          showToast(t('toast.remoteActive'), 'success');
        }
      } else {
        showToast(t('toast.remoteActive'), 'success');
      }
    }

    // Notify main process to update main window
    await api.config.apply(config);
    updateActiveModeBadge(config.mode);
    refreshStatus();
    refreshApiClientStatus();
  } catch (e) {
    showToast(t('toast.saveFailed') + ': ' + String(e), 'error');
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
      showToast(t('toast.backendStarted', {port: result.port}), 'success');
    } else {
      showToast(t('toast.testFailed') + ': ' + (result.error || 'Unknown'), 'error');
    }
    refreshStatus();
  } catch (e) {
    showToast(t('toast.testFailed') + ': ' + String(e), 'error');
  } finally {
    btn.disabled = false;
  }
}

async function stopBackend() {
  const btn = document.getElementById('btnStop');
  btn.disabled = true;
  try {
    await api.backend.stop();
    showToast(t('toast.backendStopped'), 'info');
    refreshStatus();
  } catch (e) {
    showToast(t('toast.testFailed') + ': ' + String(e), 'error');
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
      showToast(t('toast.backendRestarted', {port: result.port}), 'success');
    } else {
      showToast(t('toast.testFailed') + ': ' + (result.error || 'Unknown'), 'error');
    }
    refreshStatus();
  } catch (e) {
    showToast(t('toast.testFailed') + ': ' + String(e), 'error');
  } finally {
    btn.disabled = false;
  }
}

// --- Status ---
function refreshStatus() {
  api.backend.status().then(status => {
    updateStatusUI(status);
    if (document.getElementById('allowExternal').checked && status.running) {
      updateNetworkInfo();
    }
  }).catch(e => {
    log.error('[Settings] Failed to get backend status:', e);
  });
}

function updateStatusUI(status) {
  const bar = document.getElementById('statusBar');
  const text = document.getElementById('statusText');
  const detail = document.getElementById('statusDetail');
  const btnStart = document.getElementById('btnStart');
  const btnStop = document.getElementById('btnStop');
  const btnRestart = document.getElementById('btnRestart');

  if (status.starting) {
    bar.className = 'status-bar starting';
    text.textContent = t('backend.starting');
    detail.style.display = 'none';
    // Disable ALL buttons during startup — prevent duplicate start
    btnStart.style.display = '';
    btnStart.disabled = true;
    btnStop.style.display = 'none';
    btnRestart.style.display = 'none';
    return;
  }

  bar.className = 'status-bar ' + (status.running ? 'running' : (status.error ? 'error' : 'stopped'));

  if (status.running) {
    text.textContent = t('backend.running');
    detail.style.display = 'flex';
    document.getElementById('detailPort').textContent = status.port || '-';
    document.getElementById('detailPid').textContent = status.pid || '-';
    btnStart.style.display = 'none';
    btnStop.style.display = '';
    btnRestart.style.display = '';
  } else {
    text.textContent = status.error || t('backend.stopped');
    detail.style.display = 'none';
    btnStart.style.display = '';
    btnStop.style.display = 'none';
    btnRestart.style.display = 'none';
  }
}

// --- External Access ---
function toggleExternalAccess() {
  updateNetworkVisibility();
}

function updateNetworkVisibility() {
  const checked = document.getElementById('allowExternal').checked;
  const el = document.getElementById('networkInfo');
  if (checked) {
    el.style.display = 'block';
    updateNetworkInfo();
  } else {
    el.style.display = 'none';
  }
}

async function updateNetworkInfo() {
  const status = await api.gateway.status();
  if (!status.running || !status.port) return;
  let addresses;
  try {
    addresses = await api.getNetworkAddresses();
  } catch { return; }

  const container = document.getElementById('networkUrls');
  const port = status.port;
  let html = '<div class="network-url-line"><span class="prefix">➜  ' + t('network.local') + ':   </span><span class="url">http://localhost:' + port + '/</span></div>';
  for (const addr of addresses) {
    html += '<div class="network-url-line"><span class="prefix">➜  ' + t('network.network') + ': </span><span class="url">http://' + addr + ':' + port + '/</span></div>';
  }
  container.innerHTML = html;
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
        showToast(url + ' ' + t('toast.testSuccess'), 'success');
      } else {
        showToast(url + ' ' + t('toast.testFailed') + ': ' + (result.error || 'HTTP ' + result.status), 'error');
      }
    } else {
      const status = await api.backend.status();
      if (status.running) {
        showToast(t('toast.testBackendRunning', {port: status.port}), 'success');
      } else {
        showToast(t('toast.testBackendNotRunning'), 'error');
      }
    }
  } catch (e) {
    log.error('Connection test error:', e);
    showToast(t('toast.connectionTestFailed') + ': ' + (e && e.message ? e.message : String(e)), 'error');
  } finally {
    btn.disabled = false;
    btn.classList.remove('btn-loading');
  }
}

// --- API Clients (multiple) ---

function escapeHtml(str) {
  return String(str == null ? '' : str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function apiClientCardHtml(index, client) {
  const id = client?.backendId || '';
  const label = escapeHtml(client?.name || ('Client ' + (index + 1)));
  return '' +
    '<div class="api-client-card" data-index="' + index + '" data-backend-id="' + escapeHtml(id) + '">' +
      '<div class="api-client-header">' +
        '<span class="api-client-title">' + label + '</span>' +
        '<button class="btn btn-danger btn-sm" onclick="removeApiClientCard(' + index + ')">' + t('apiClient.remove') + '</button>' +
      '</div>' +
      '<div class="form-group">' +
        '<label class="form-label">' + t('apiClient.name') + '</label>' +
        '<input type="text" id="apiClientName_' + index + '" data-field="name" value="' + escapeHtml(client?.name || '') + '" placeholder="' + t('apiClient.name.placeholder') + '" onchange="saveApiClientField(this, this.value)">' +
      '</div>' +
      '<div class="form-group">' +
        '<label class="form-label">' + t('apiClient.rootDir') + '</label>' +
        '<input type="text" id="apiClientRootDir_' + index + '" data-field="rootDir" value="' + escapeHtml(client?.rootDir || '') + '" placeholder="C:\\\\Users\\\\xxx\\\\projects" onchange="saveApiClientField(this, this.value)">' +
        '<div class="form-hint">' + t('apiClient.rootDir.hint') + '</div>' +
      '</div>' +
      '<div class="form-group">' +
        '<label class="switch-label">' +
          '<span class="switch">' +
            '<input type="checkbox" id="apiClientAutoStart_' + index + '" data-field="autoStart"' + (client?.autoStart ? ' checked' : '') + ' onchange="saveApiClientField(this, this.checked)">' +
            '<span class="switch-slider"></span>' +
          '</span>' +
          '<span>' + t('apiClient.autoStart') + '</span>' +
        '</label>' +
      '</div>' +
      '<div class="status-bar stopped" id="apiClientStatusBar_' + index + '">' +
        '<span class="dot"></span>' +
        '<span id="apiClientStatusText_' + index + '">' + t('apiClient.status.disconnected') + '</span>' +
      '</div>' +
      '<div class="api-client-id" id="apiClientRegisteredId_' + index + '"></div>' +
      '<div class="btn-row">' +
        '<button class="btn btn-primary" id="btnApiClientStart_' + index + '" onclick="startApiClient(' + index + ')">' + t('apiClient.start') + '</button>' +
        '<button class="btn btn-danger" id="btnApiClientStop_' + index + '" onclick="stopApiClient(' + index + ')" style="display:none;">' + t('apiClient.stop') + '</button>' +
        '<button class="btn btn-default" id="btnApiClientRestart_' + index + '" onclick="restartApiClient(' + index + ')" style="display:none;">' + t('apiClient.restart') + '</button>' +
        '<button class="btn btn-success" id="btnApiClientRegister_' + index + '" onclick="registerApiClient(' + index + ')">' + t('apiClient.register') + '</button>' +
      '</div>' +
    '</div>';
}

function renderApiClientCards() {
  const container = document.getElementById('apiClientList');
  if (!container) return;
  const clients = currentConfig?.remote?.apiClients || [];
  if (clients.length === 0) {
    container.innerHTML = '<div class="api-client-empty">' + t('apiClient.empty') + '</div>';
    return;
  }
  container.innerHTML = clients.map((c, i) => apiClientCardHtml(i, c)).join('');
  clients.forEach((c, i) => updateApiClientCardRegistered(i, c));
  refreshApiClientStatus();
}

function addApiClientCard() {
  if (!currentConfig) return;
  if (!currentConfig.remote) currentConfig.remote = {};
  if (!currentConfig.remote.apiClients) currentConfig.remote.apiClients = [];
  currentConfig.remote.apiClients.push({ name: '', backendId: '', apiKey: '', rootDir: '', autoStart: false });
  api.config.update(currentConfig);
  renderApiClientCards();
}

async function removeApiClientCard(index) {
  if (!currentConfig?.remote?.apiClients) return;
  const client = currentConfig.remote.apiClients[index];
  if (!client) return;
  if (client.backendId) {
    try { await api.apibackend.remove(client.backendId); } catch (e) { /* ignore */ }
  }
  currentConfig.remote.apiClients.splice(index, 1);
  await api.config.update(currentConfig);
  renderApiClientCards();
  showToast(t('apiClient.removed'), 'info');
}

function saveApiClientField(input, value) {
  if (!currentConfig?.remote?.apiClients) return;
  const card = input.closest('.api-client-card');
  if (!card) return;
  const index = parseInt(card.getAttribute('data-index'), 10);
  const field = input.getAttribute('data-field');
  const client = currentConfig.remote.apiClients[index];
  if (!client || !field) return;
  client[field] = value;
  api.config.update(currentConfig);
}

async function startApiClient(index) {
  const client = currentConfig?.remote?.apiClients?.[index];
  if (!client) return;
  if (!client.backendId) {
    showToast(t('apiClient.notRegistered'), 'warning');
    return;
  }
  const btn = document.getElementById('btnApiClientStart_' + index);
  btn.disabled = true;
  try {
    // Persist card fields so the main process uses the latest config
    await api.config.update(currentConfig);
    const result = await api.apibackend.startOne(client.backendId);
    if (result.success) {
      showToast(t('apiClient.status.connected'), 'success');
    } else {
      showToast(t('apiClient.status.error') + ': ' + (result.error || 'Unknown'), 'error');
    }
    refreshApiClientStatus();
  } catch (e) {
    showToast(t('apiClient.status.error') + ': ' + String(e), 'error');
  } finally {
    btn.disabled = false;
  }
}

async function stopApiClient(index) {
  const client = currentConfig?.remote?.apiClients?.[index];
  if (!client) return;
  const btn = document.getElementById('btnApiClientStop_' + index);
  btn.disabled = true;
  try {
    await api.apibackend.stopOne(client.backendId);
    showToast(t('apiClient.status.disconnected'), 'info');
    refreshApiClientStatus();
  } catch (e) {
    showToast(t('apiClient.status.error') + ': ' + String(e), 'error');
  } finally {
    btn.disabled = false;
  }
}

async function restartApiClient(index) {
  const client = currentConfig?.remote?.apiClients?.[index];
  if (!client) return;
  if (!client.backendId) {
    showToast(t('apiClient.notRegistered'), 'warning');
    return;
  }
  const btn = document.getElementById('btnApiClientRestart_' + index);
  btn.disabled = true;
  try {
    await api.config.update(currentConfig);
    await api.apibackend.stopOne(client.backendId);
    const result = await api.apibackend.startOne(client.backendId);
    if (result.success) {
      showToast(t('apiClient.status.connected'), 'success');
    } else {
      showToast(t('apiClient.status.error') + ': ' + (result.error || 'Unknown'), 'error');
    }
    refreshApiClientStatus();
  } catch (e) {
    showToast(t('apiClient.status.error') + ': ' + String(e), 'error');
  } finally {
    btn.disabled = false;
  }
}

async function registerApiClient(index) {
  const client = currentConfig?.remote?.apiClients?.[index];
  if (!client) return;
  const btn = document.getElementById('btnApiClientRegister_' + index);
  btn.disabled = true;
  btn.classList.add('btn-loading');
  try {
    const url = document.getElementById('remoteUrl').value.replace(/\\/+$/, '');
    const rootDir = document.getElementById('apiClientRootDir_' + index).value;
    const name = document.getElementById('apiClientName_' + index).value;
    const result = await api.apibackend.register(url, rootDir, name);
    if (result.success) {
      // Update currentConfig so gatherConfig picks up the new credentials
      if (!currentConfig) currentConfig = {};
      if (!currentConfig.remote) currentConfig.remote = {};
      if (!currentConfig.remote.apiClients) currentConfig.remote.apiClients = [];
      const target = currentConfig.remote.apiClients[index];
      if (target) {
        target.backendId = result.backendId;
        target.apiKey = result.apiKey;
        target.rootDir = rootDir;
        target.name = name || '';
      }

      // Also persist the updated config to disk immediately
      await api.config.update(currentConfig);

      renderApiClientCards();
      showToast(t('apiClient.registered', {id: result.backendId}), 'success');
    } else {
      showToast(t('apiClient.registerFailed') + ': ' + (result.error || 'Unknown'), 'error');
    }
  } catch (e) {
    showToast(t('apiClient.registerFailed') + ': ' + String(e), 'error');
  } finally {
    btn.disabled = false;
    btn.classList.remove('btn-loading');
  }
}

function refreshApiClientStatus() {
  api.apibackend.status().then(statuses => {
    updateApiClientStatusUI(statuses);
  }).catch(e => {
    log.error('[Settings] Failed to get API client status:', e);
  });
}

function updateApiClientStatusUI(statuses) {
  if (!Array.isArray(statuses)) statuses = [statuses];
  statuses.forEach(status => {
    if (!status || !status.backendId) return;
    const card = document.querySelector('.api-client-card[data-backend-id="' + status.backendId + '"]');
    if (!card) return;
    const idx = card.getAttribute('data-index');
    const bar = document.getElementById('apiClientStatusBar_' + idx);
    const text = document.getElementById('apiClientStatusText_' + idx);
    const btnStart = document.getElementById('btnApiClientStart_' + idx);
    const btnStop = document.getElementById('btnApiClientStop_' + idx);
    const btnRestart = document.getElementById('btnApiClientRestart_' + idx);
    if (!bar || !text || !btnStart || !btnStop || !btnRestart) return;

    if (status.connecting) {
      bar.className = 'status-bar starting';
      text.textContent = t('apiClient.status.connecting');
      btnStart.style.display = 'none';
      btnStop.style.display = 'none';
      btnRestart.style.display = 'none';
      return;
    }

    if (status.connected) {
      bar.className = 'status-bar running';
      text.textContent = t('apiClient.status.connected');
      btnStart.style.display = 'none';
      btnStop.style.display = '';
      btnRestart.style.display = '';
    } else {
      bar.className = 'status-bar ' + (status.error && status.error !== 'Not connected' ? 'error' : 'stopped');
      text.textContent = status.error && status.error !== 'Not connected' ? status.error : t('apiClient.status.disconnected');
      btnStart.style.display = '';
      btnStop.style.display = 'none';
      btnRestart.style.display = 'none';
    }
  });
}

function updateApiClientCardRegistered(index, client) {
  const el = document.getElementById('apiClientRegisteredId_' + index);
  if (!el) return;
  const btn = document.getElementById('btnApiClientRegister_' + index);
  if (client && client.backendId) {
    el.className = 'api-client-id registered';
    el.textContent = t('apiClient.registered', {id: client.backendId});
    if (btn) btn.style.display = 'none';
  } else {
    el.className = 'api-client-id';
    el.textContent = t('apiClient.notRegistered');
    if (btn) btn.style.display = '';
  }
}

// --- Init ---
async function init() {
  try {
    const config = await api.config.get();
    applyConfigToUI(config);

    // Get config path
    const path = await api.config.getPath();
    document.getElementById('configPath').textContent = t('config.path') + ': ' + path;

    // Subscribe to backend status changes
    statusCleanup = api.backend.onStatusChange(status => updateStatusUI(status));

    // Subscribe to runtime extraction progress
    api.runtime.onExtractionProgress(progress => {
      if (progress.phase === 'extracting') {
        const bar = document.getElementById('statusBar');
        const text = document.getElementById('statusText');
        const detail = document.getElementById('statusDetail');
        if (bar && bar.classList.contains('starting')) {
          text.textContent = progress.detail;
          detail.style.display = 'flex';
          const detailPort = document.getElementById('detailPort');
          const detailPid = document.getElementById('detailPid');
          if (detailPort) detailPort.textContent = progress.percent + '%';
          if (detailPid) detailPid.textContent = progress.phase;
        }
      }
    });

    refreshStatus();
    refreshApiClientStatus();

    // Subscribe to API client status changes
    const apiClientCleanup = api.apibackend.onStatusChange(status => updateApiClientStatusUI(status));

    // Override cleanup to include apiClient
    const origCleanup = window.onbeforeunload;
    window.addEventListener('beforeunload', () => {
      if (statusCleanup) statusCleanup();
      if (apiClientCleanup) apiClientCleanup();
    });
  } catch (e) {
    showToast(t('toast.loadFailed') + ': ' + String(e), 'error');
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
    frame: false,
    titleBarStyle: 'hidden',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  settingsWindow.setMenu(null)
  settingsWindow.loadURL(getSettingsHtml())

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

  ipcMain.handle('get-network-addresses', () => {
    const interfaces = os.networkInterfaces()
    const addresses: string[] = []
    for (const name of Object.keys(interfaces)) {
      for (const iface of interfaces[name]!) {
        // Skip internal (loopback) and non-IPv4 addresses
        if (!iface.internal && iface.family === 'IPv4') {
          addresses.push(iface.address)
        }
      }
    }
    return addresses
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
      // Test connectivity by requesting the root; any HTTP response (including 3xx/4xx)
      // proves the server is reachable. Only network errors / timeouts mean failure.
      const req = http.get(cleanUrl + '/', { timeout: 15000 }, (res) => {
        res.resume()
        res.on('end', () => {
          resolve({ ok: true, status: res.statusCode })
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
