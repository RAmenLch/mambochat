/**
 * URL resolver for Electron vs browser environments.
 *
 * When running inside Electron with the embedded gateway, the frontend uses
 * relative paths for API requests and file URLs. The gateway server proxies
 * /api/* to the actual backend (local or remote), so no URL rewriting is needed.
 *
 * This module provides a compatibility layer for SSE connections and file URLs
 * that historically needed full URL construction.
 */

let currentBaseUrl = ''

/**
 * Set the current backend base URL.
 *
 * In gateway mode, this is empty (relative paths are used).
 * Kept for backward compatibility.
 */
export function setBackendBaseUrl(url: string): void {
  currentBaseUrl = url
}

/**
 * Resolve a relative API path to a full URL.
 *
 * In browser mode: returns the path as-is (relative, proxied by Vite).
 * In Electron gateway mode: returns the path as-is (relative, proxied by gateway).
 *
 * @param path - Relative path, e.g. "/api/chats/123/stream-response/456"
 * @returns Resolved URL
 */
export function resolveApiUrl(path: string): string {
  if (!path.startsWith('/')) {
    return path
  }

  const isElectron = !!(window as unknown as Record<string, unknown>).__mambochat_electron__
  if (!isElectron || !currentBaseUrl) {
    // Browser mode or gateway mode: use relative path
    return path
  }

  // Fallback: if a full backend URL was set (legacy), prepend it
  return `${currentBaseUrl}${path}`
}

/**
 * Resolve a file URL (e.g., avatar, image download path) for use in <img src> etc.
 *
 * In browser mode: returns the path as-is (Vite proxy handles it).
 * In Electron gateway mode: returns the path as-is (gateway proxy handles it).
 *
 * @param url - File URL, e.g. "/api/files/download/avatars/xxx.png"
 * @returns Resolved URL
 */
export function resolveFileUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined
  if (!url.startsWith('/')) return url
  return resolveApiUrl(url)
}
