/**
 * Data directory management for the MamboChat desktop app.
 *
 * Problem:  In the packaged app, the backend stores DB and uploads relative
 *           to its own directory (resources/DB, resources/uploads). The install
 *           directory (e.g. C:\Program Files) is not writable by normal users.
 *
 * Solution: Pass the persistent user-data root to the backend via the
 *           DATA_DIR / STORAGE_PATH environment variables. The backend reads
 *           those and stores everything under %AppData%/mambochat-desktop/data/
 *           — or under a user-chosen custom directory configured in the desktop
 *           settings (Local Mode → Data Directory), so the DBs can live on a
 *           drive with more space.
 *
 * The backend code falls back to relative paths when the env vars are absent,
 * so Docker and dev mode are unaffected — this module is only invoked in the
 * packaged Electron build.
 */

import { app } from 'electron'
import { join, resolve, sep } from 'path'
import { mkdirSync, existsSync } from 'fs'
import { cp, readdir, rm } from 'fs/promises'
import log from './log'

const DATA_SUBDIR = 'data'

/**
 * Returns the default persistent user data root.
 * Each Electron app instance gets its own userData, so multiple installs
 * on the same machine naturally have separate data directories.
 */
export function getDefaultDataDirectory(): string {
  return join(app.getPath('userData'), DATA_SUBDIR)
}

/**
 * Returns the persistent data directory to use.
 * Prefers the user-configured custom directory (empty string falls back to
 * the default under Electron userData). Empty string in dev mode (backend
 * uses its own relative paths).
 */
export function getDataDirectory(dataDir?: string): string {
  if (!app.isPackaged) {
    return ''
  }
  if (dataDir && dataDir.trim()) {
    return dataDir.trim()
  }
  return getDefaultDataDirectory()
}

/**
 * Main entry point — call once before starting the backend.
 *
 * Ensures persistent data directories exist (under the custom data dir when
 * configured, otherwise the Electron userData path). In development mode
 * this is a no-op.
 */
export function setupDataDirectories(dataDir?: string): void {
  if (!app.isPackaged) {
    return
  }

  const dataRoot = getDataDirectory(dataDir)

  // Pre-create directories so the backend never needs to mkdir
  mkdirSync(join(dataRoot, 'DB'), { recursive: true })
  mkdirSync(join(dataRoot, 'uploads'), { recursive: true })

  log.info(`[DataDir] Data root: ${dataRoot}`)
}

/**
 * Migrate all contents of the old data directory into a new one.
 *
 * Copies every entry (DB/, uploads/ and any future subdirectories) from
 * `from` to `to`. When `deleteOld` is true the old directory is removed
 * afterwards to free disk space. Existing files in the target are
 * overwritten, so re-running a migration is safe.
 *
 * Refuses to migrate when the target is inside the source (would recurse).
 */
export async function migrateDataDirectory(
  from: string,
  to: string,
  deleteOld: boolean
): Promise<{ from: string; to: string; copied: number }> {
  const fromResolved = resolve(from)
  const toResolved = resolve(to)

  if (fromResolved === toResolved) {
    return { from, to, copied: 0 }
  }
  if (toResolved.startsWith(fromResolved + sep)) {
    throw new Error('Target directory must not be inside the source directory')
  }

  mkdirSync(toResolved, { recursive: true })

  let copied = 0
  if (existsSync(fromResolved)) {
    const entries = await readdir(fromResolved, { withFileTypes: true })
    for (const entry of entries) {
      await cp(join(fromResolved, entry.name), join(toResolved, entry.name), {
        recursive: true,
        force: true,
      })
      copied++
    }
  }

  if (deleteOld) {
    await rm(fromResolved, { recursive: true, force: true })
  }

  log.info(`[DataDir] Migrated ${fromResolved} -> ${toResolved} (${copied} entries${deleteOld ? ', old deleted' : ''})`)
  return { from, to, copied }
}
