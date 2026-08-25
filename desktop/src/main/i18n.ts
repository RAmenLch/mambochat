/**
 * Desktop i18n - Independent internationalization for the desktop application.
 *
 * Provides translations for the settings window and other desktop-specific UI elements.
 * This is separate from the frontend's vue-i18n system.
 */

import { app } from 'electron'

export type DesktopLocale = 'zh-CN' | 'en'

export interface DesktopTranslations {
  [key: string]: string
}

export const translations: Record<DesktopLocale, DesktopTranslations> = {
  'zh-CN': {
    // Title
    'settings.title': 'MamboChat 桌面设置',
    // Connection Mode
    'mode.title': '连接模式',
    'mode.local': '本地模式',
    'mode.local.desc': '在本地运行后端服务',
    'mode.remote': '远程模式',
    'mode.remote.desc': '连接到远程服务器',
    'mode.current': '当前模式',
    'mode.current.local': '本地模式',
    'mode.current.remote': '远程模式',
    'mode.test': '测试连接',
    'mode.save': '保存并应用',
    // Local Backend
    'local.title': '本地后端',
    'local.host': '主机地址',
    'local.portRange': '端口范围',
    'local.pythonPath': 'Python 路径',
    'local.pythonPath.hint': 'Python 可执行文件的路径。相对路径将从应用资源目录解析。',
    'local.externalAccess': '允许外部网络访问',
    'local.externalAccess.hint': '将网关服务器绑定到 0.0.0.0，以便同一网络中的其他设备可以通过浏览器访问。',
    'local.gatewayPort': '网关端口',
    'local.gatewayPort.hint': '内嵌网关服务器的端口。更改此值需要重启网关。',
    'local.networkUrls': '网络访问地址',
    // Backend Status
    'backend.checking': '检查中...',
    'backend.running': '后端运行中',
    'backend.stopped': '后端已停止',
    'backend.starting': '正在启动...',
    'backend.start': '启动',
    'backend.stop': '停止',
    'backend.restart': '重启',
    // Remote Server
    'remote.title': '远程服务器',
    'remote.serverUrl': '服务器地址',
    'remote.serverUrl.hint': '远程 MamboChat 后端服务器的基础 URL。',
    // API Client
    'apiClient.title': 'API 客户端（将本机注册为远端 Backend）',
    'apiClient.name': '名称',
    'apiClient.name.placeholder': '给该客户端起个名字（可选）',
    'apiClient.add': '添加客户端',
    'apiClient.remove': '移除',
    'apiClient.removed': '客户端已移除',
    'apiClient.empty': '还没有 API 客户端，点击右上角"添加客户端"创建一个',
    'apiClient.rootDir': '本地根目录',
    'apiClient.rootDir.hint': '远端 Agent 将能访问此目录下的文件。留空则默认使用用户主目录。',
    'apiClient.autoStart': '切换远程模式时自动连接',
    'apiClient.status.connected': '已连接',
    'apiClient.status.disconnected': '未连接',
    'apiClient.status.connecting': '连接中...',
    'apiClient.status.error': '连接失败',
    'apiClient.start': '连接',
    'apiClient.stop': '断开',
    'apiClient.restart': '重连',
    'apiClient.register': '注册到远端',
    'apiClient.registered': '已注册: {id}',
    'apiClient.notRegistered': '尚未注册，请先点击"注册到远端"',
    'apiClient.registerFailed': '注册失败',
    // Toast Messages
    'toast.saved': '配置已保存',
    'toast.savedAndApplied': '配置已保存并应用',
    'toast.gatewayRestartFailed': '网关重启失败',
    'toast.remoteActive': '配置已保存，远程模式已激活',
    'toast.saveFailed': '保存失败',
    'toast.backendStarted': '后端已在端口 {port} 启动',
    'toast.backendStopped': '后端已停止',
    'toast.backendRestarted': '后端已在端口 {port} 重启',
    'toast.testSuccess': '连接成功！',
    'toast.testFailed': '连接失败',
    'toast.testBackendRunning': '后端正在端口 {port} 运行',
    'toast.testBackendNotRunning': '后端未运行',
    'toast.loadFailed': '加载配置失败',
    'toast.connectionTestFailed': '连接测试失败',
    // Config
    'config.path': '配置文件',
    // Status
    'status.port': '端口',
    'status.pid': 'PID',
    'network.local': '本地',
    'network.network': '网络',
    // Title Bar
    'titlebar.minimize': '最小化',
    'titlebar.maximize': '最大化',
    'titlebar.close': '关闭',
    // Tray
    'tray.show': '显示窗口',
    'tray.quit': '退出 MamboChat',
    // Error Messages
    'error.backendControlLocalOnly': '后端控制仅在本地模式下可用',
    // Runtime Extraction
    'runtime.checking': '正在准备运行时环境...',
    'runtime.counting': '正在扫描压缩包...',
    'runtime.extracting': '正在解压运行时环境...',
    'runtime.extractingPercent': '正在解压运行时环境 ({percent}%)...',
    'runtime.done': '运行时环境解压完成',
    'runtime.archiveNotFound': '未找到运行时压缩包，安装可能已损坏',
    'runtime.extractionError': '解压出错',
    'runtime.extractionIncomplete': '解压不完整',
    'runtime.extractionFinalizeFailed': '解压收尾失败',
    'runtime.pythonNotFound': '解压完成但未找到 python.exe',
  },
  'en': {
    // Title
    'settings.title': 'MamboChat Desktop Settings',
    // Connection Mode
    'mode.title': 'Connection Mode',
    'mode.local': 'Local',
    'mode.local.desc': 'Run backend locally',
    'mode.remote': 'Remote',
    'mode.remote.desc': 'Connect to remote server',
    'mode.current': 'Current Mode',
    'mode.current.local': 'Local Mode',
    'mode.current.remote': 'Remote Mode',
    'mode.test': 'Test Connection',
    'mode.save': 'Save & Apply',
    // Local Backend
    'local.title': 'Local Backend',
    'local.host': 'Host',
    'local.portRange': 'Port Range',
    'local.pythonPath': 'Python Path',
    'local.pythonPath.hint': 'Path to the Python executable. Relative paths are resolved from the app resources directory.',
    'local.externalAccess': 'Allow external network access',
    'local.externalAccess.hint': 'Bind the gateway server to 0.0.0.0 so other devices on the same network can access it via browser.',
    'local.gatewayPort': 'Gateway Port',
    'local.gatewayPort.hint': 'Port for the embedded gateway server. Changing this requires a gateway restart.',
    'local.networkUrls': 'Network Access URLs',
    // Backend Status
    'backend.checking': 'Checking...',
    'backend.running': 'Backend Running',
    'backend.stopped': 'Backend Stopped',
    'backend.starting': 'Starting...',
    'backend.start': 'Start',
    'backend.stop': 'Stop',
    'backend.restart': 'Restart',
    // Remote Server
    'remote.title': 'Remote Server',
    'remote.serverUrl': 'Server URL',
    'remote.serverUrl.hint': 'The base URL of the remote MamboChat backend server.',
    // API Client
    'apiClient.title': 'API Client (Register this PC as Remote Backend)',
    'apiClient.name': 'Name',
    'apiClient.name.placeholder': 'A friendly label for this client (optional)',
    'apiClient.add': 'Add Client',
    'apiClient.remove': 'Remove',
    'apiClient.removed': 'Client removed',
    'apiClient.empty': 'No API clients yet. Click "Add Client" in the top-right to create one.',
    'apiClient.rootDir': 'Local Root Directory',
    'apiClient.rootDir.hint': 'The remote agent will be able to access files under this directory. Leave empty to use the home directory.',
    'apiClient.autoStart': 'Auto-connect when switching to remote mode',
    'apiClient.status.connected': 'Connected',
    'apiClient.status.disconnected': 'Disconnected',
    'apiClient.status.connecting': 'Connecting...',
    'apiClient.status.error': 'Connection Error',
    'apiClient.start': 'Connect',
    'apiClient.stop': 'Disconnect',
    'apiClient.restart': 'Reconnect',
    'apiClient.register': 'Register with Server',
    'apiClient.registered': 'Registered: {id}',
    'apiClient.notRegistered': 'Not registered. Click "Register with Server" first.',
    'apiClient.registerFailed': 'Registration failed',
    // Toast Messages
    'toast.saved': 'Config saved',
    'toast.savedAndApplied': 'Config saved and applied',
    'toast.gatewayRestartFailed': 'Gateway restart failed',
    'toast.remoteActive': 'Config saved, remote mode active',
    'toast.saveFailed': 'Save failed',
    'toast.backendStarted': 'Backend started on port {port}',
    'toast.backendStopped': 'Backend stopped',
    'toast.backendRestarted': 'Backend restarted on port {port}',
    'toast.testSuccess': 'Connection successful!',
    'toast.testFailed': 'Connection failed',
    'toast.testBackendRunning': 'Backend is running on port {port}',
    'toast.testBackendNotRunning': 'Backend is not running',
    'toast.loadFailed': 'Failed to load config',
    'toast.connectionTestFailed': 'Connection test failed',
    // Config
    'config.path': 'Config',
    // Status
    'status.port': 'Port',
    'status.pid': 'PID',
    'network.local': 'Local',
    'network.network': 'Network',
    // Title Bar
    'titlebar.minimize': 'Minimize',
    'titlebar.maximize': 'Maximize',
    'titlebar.close': 'Close',
    // Tray
    'tray.show': 'Show Window',
    'tray.quit': 'Quit MamboChat',
    // Error Messages
    'error.backendControlLocalOnly': 'Backend control is only available in local mode',
    // Runtime Extraction
    'runtime.checking': 'Preparing runtime environment...',
    'runtime.counting': 'Scanning archive...',
    'runtime.extracting': 'Extracting runtime...',
    'runtime.extractingPercent': 'Extracting runtime ({percent}%)...',
    'runtime.done': 'Runtime extraction complete',
    'runtime.archiveNotFound': 'Runtime archive not found. Installation may be corrupted',
    'runtime.extractionError': 'Extraction error',
    'runtime.extractionIncomplete': 'Extraction incomplete',
    'runtime.extractionFinalizeFailed': 'Failed to finalize extraction',
    'runtime.pythonNotFound': 'Extraction finished but python.exe not found',
  },
}

/**
 * Detect the system locale and return the matching DesktopLocale.
 */
export function getDesktopLocale(): DesktopLocale {
  const sysLocale = app.getLocale()
  if (sysLocale.startsWith('zh')) return 'zh-CN'
  return 'en'
}

/**
 * Translate a key with optional parameters.
 */
export function translate(locale: DesktopLocale, key: string, params?: Record<string, string | number>): string {
  let text = translations[locale]?.[key] ?? translations['en']?.[key] ?? key
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      text = text.replace(`{${k}}`, String(v))
    }
  }
  return text
}
