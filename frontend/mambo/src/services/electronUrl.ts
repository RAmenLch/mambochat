/**
 * URL resolver for Electron vs browser environments.
 *
 * In browser mode, SSE and API requests use relative paths (/api/*).
 * In Electron mode, these need to be resolved against the dynamic backend URL.
 */

let currentBaseUrl = '/api'

/**
 * Set the current backend base URL (without trailing /api).
 * e.g., "http://127.0.0.1:8000"
 */
export function setBackendBaseUrl(url: string): void {
  currentBaseUrl = url
}

/**
 * Resolve a relative API path to a full URL.
 *
 * In browser mode, returns the path as-is (relative).
 * In Electron mode, prepends the backend base URL.
 *
 * @param path - Relative path, e.g. "/api/chats/123/stream-response/456"
 * @returns Resolved URL
 */
export function resolveApiUrl(path: string): string {
  if (!path.startsWith('/')) {
    return path
  }

  const isElectron = !!(window as any).__mambochat_electron__
  if (!isElectron) {
    return path
  }

  return `${currentBaseUrl}${path}`
}
