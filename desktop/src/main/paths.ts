/**
 * Data directory management for the MamboChat desktop app.
 *
 * Problem:  In the packaged app, the backend stores DB and uploads relative
 *           to its own directory (resources/DB, resources/uploads). The install
 *           directory (e.g. C:\Program Files) is not writable by normal users.
 *
 * Solution: Pass the persistent user-data root to the backend via the
 *           DATA_DIR / STORAGE_PATH environment variables. The backend reads
 *           those and stores everything under %AppData%/MamboChat/data/.
 *
 * The backend code falls back to relative paths when the env vars are absent,
 * so Docker and dev mode are unaffected — this module is only invoked in the
 * packaged Electron build.
 */

import { app } from 'electron'
import { join } from 'path'
import { mkdirSync } from 'fs'
import log from './log'

const DATA_SUBDIR = 'data'

/**
 * Returns the persistent user data root.
 * Each Electron app instance gets its own userData, so multiple installs
 * on the same machine naturally have separate data directories.
 */
function getUserDataRoot(): string {
  return join(app.getPath('userData'), DATA_SUBDIR)
}

/**
 * Returns the persistent data directory for use in environment variables.
 * Empty string in dev mode (backend uses its own relative paths).
 */
export function getDataDirectory(): string {
  if (!app.isPackaged) {
    return ''
  }
  return getUserDataRoot()
}

/**
 * Main entry point — call once before starting the backend.
 *
 * Ensures persistent data directories exist under the Electron userData path.
 * In development mode this is a no-op.
 */
export function setupDataDirectories(): void {
  if (!app.isPackaged) {
    return
  }

  const userDataRoot = getUserDataRoot()

  // Pre-create directories so the backend never needs to mkdir
  mkdirSync(join(userDataRoot, 'DB'), { recursive: true })
  mkdirSync(join(userDataRoot, 'uploads'), { recursive: true })

  log.info(`[DataDir] Data root: ${userDataRoot}`)
}
