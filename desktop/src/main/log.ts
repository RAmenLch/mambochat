/**
 * Centralized logging for the Electron main process.
 *
 * Uses electron-log to write logs to both the console and a rotating log file.
 * Log files are stored under the user data directory:
 *   - Windows: %APPDATA%/mambochat-desktop/logs/
 *   - macOS:   ~/Library/Logs/mambochat-desktop/
 *   - Linux:   ~/.config/mambochat-desktop/logs/
 */

import log from 'electron-log/main'

// Log file settings
log.transports.file.maxSize = 5 * 1024 * 1024 // 5 MB per file
log.transports.file.format = '[{y}-{m}-{d} {h}:{i}:{s}] [{level}] {text}'
log.transports.console.format = '[{level}] {text}'

// Resolve the log file location for display purposes
export function getLogPath(): string {
  return log.transports.file.getFile().path
}

// Re-export log as the default logger
export default log
