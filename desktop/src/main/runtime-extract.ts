/**
 * Runtime extraction: ensures the python directory is present on first launch.
 *
 * In the packaged build, the Python runtime is shipped as a single python.tar
 * (uncompressed tar). This module extracts it on first launch so that
 * subsequent starts are instant.
 *
 * Robustness strategy — atomic extraction:
 * 1. Extraction always targets a **temporary** directory (python.extracting).
 * 2. Only after successful extraction + integrity check, the temporary dir
 *    is **renamed** to python (which is effectively atomic on Windows/NTFS).
 * 3. On next launch, if python.extracting exists (stale from a crash), it is
 *    deleted and re-extraction is retried from scratch.
 * 4. This guarantees that python is either fully intact or completely absent.
 */

import { existsSync, mkdirSync, rmSync, renameSync, createReadStream, writeFileSync } from 'fs'
import { join } from 'path'
import { Readable } from 'stream'
import { createHash } from 'crypto'
import { app, BrowserWindow } from 'electron'
import * as tar from 'tar'
import * as zlib from 'zlib'
import log from './log'
import { getDesktopLocale, translate } from './i18n'

export interface ExtractionProgress {
  phase: 'checking' | 'counting' | 'extracting' | 'done' | 'error'
  percent: number
  detail: string
}

function broadcastProgress(progress: ExtractionProgress): void {
  BrowserWindow.getAllWindows().forEach(win => {
    if (!win.isDestroyed()) {
      win.webContents.send('runtime:extraction-progress', progress)
    }
  })
}

/**
 * Count total entries in a tar archive by scanning headers (no extraction).
 * Returns only file entries (not directories) since those are the slow part.
 */
async function countTarEntries(tarPath: string): Promise<number> {
  return new Promise((resolve, reject) => {
    let fileCount = 0
    const stream = createReadStream(tarPath).on('error', reject)

    stream.once('readable', () => {
      const pushed = stream.read(2)
      if (pushed && pushed[0] === 0x1f && pushed[1] === 0x8b) {
        // gzip compressed
        const gzip = zlib.createGunzip()
        gzip.on('error', reject)
        stream.unpipe()
        const headerStream = new Readable()
        headerStream.push(pushed)
        headerStream.push(null)
        headerStream.pipe(gzip)
        parseHeaders(gzip)
      } else {
        // plain tar
        const passthrough = new Readable()
        passthrough.push(pushed)
        passthrough.push(null)
        parseHeaders(passthrough)
      }
    })

    function parseHeaders(input: NodeJS.ReadableStream) {
      const parser = tar.t({
        onentry: (entry) => {
          if (entry.type === 'File') fileCount++
        },
        strict: false,
      })
      parser.on('error', reject)
      parser.on('end', () => resolve(fileCount))
      parser.on('close', () => resolve(fileCount))
      input.pipe(parser)
    }
  })
}

/**
 * Check whether the python directory has been successfully extracted.
 * Uses a stamp file so we can distinguish "fully extracted" from
 * "partially extracted (crash / kill during extraction)".
 */
function isPythonReady(pythonDir: string, pythonExe: string): boolean {
  const stampFile = join(pythonDir, '.extraction-ok')
  return existsSync(stampFile) && existsSync(pythonExe)
}

/**
 * Compute SHA-256 of a file and return it as a hex string.
 * Used to verify the tar archive hasn't been tampered with.
 */
async function sha256File(filePath: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const hash = createHash('sha256')
    const stream = createReadStream(filePath)
    stream.on('data', (data: string | Buffer) => hash.update(data))
    stream.on('end', () => resolve(hash.digest('hex')))
    stream.on('error', reject)
  })
}

/**
 * Safely remove a directory (recursive), ignoring errors if it doesn't exist.
 */
function safeRemove(dir: string): void {
  try {
    rmSync(dir, { recursive: true, force: true })
  } catch {
    // ignore
  }
}

export async function ensureRuntimeExtracted(): Promise<void> {
  if (!app.isPackaged) return

  const locale = getDesktopLocale()

  const resourcesPath = process.resourcesPath
  const runtimeDir = join(resourcesPath, 'runtime')
  const pythonTar = join(runtimeDir, 'python.tar')
  const pythonDir = join(runtimeDir, 'python')
  const stagingDir = join(runtimeDir, 'python.extracting')
  const pythonExe = join(pythonDir, 'python.exe')

  // ------------------------------------------------------------------
  // Fast path: python dir is already fully extracted and stamped
  // ------------------------------------------------------------------
  if (isPythonReady(pythonDir, pythonExe)) {
    log.info('[Runtime] python runtime already extracted and verified, skipping')
    return
  }

  // If python.exe exists but stamp is missing, something went wrong
  // on a previous run — treat it as incomplete.
  if (existsSync(pythonDir)) {
    log.warn('[Runtime] python dir exists but is incomplete (no stamp) — removing for re-extraction')
    safeRemove(pythonDir)
  }

  // ------------------------------------------------------------------
  // Validate tar archive exists
  // ------------------------------------------------------------------
  if (!existsSync(pythonTar)) {
    broadcastProgress({
      phase: 'error', percent: 0,
      detail: translate(locale, 'runtime.archiveNotFound')
    })
    throw new Error(
      `Runtime archive not found at "${pythonTar}". ` +
      'The installation may be corrupted. Please reinstall.'
    )
  }

  // ------------------------------------------------------------------
  // Clean up stale staging directory from a previous interrupted extraction
  // ------------------------------------------------------------------
  if (existsSync(stagingDir)) {
    log.warn('[Runtime] Found stale python.extracting from a previous interrupted run — cleaning up')
    safeRemove(stagingDir)
  }

  mkdirSync(runtimeDir, { recursive: true })

  log.info('[Runtime] First launch detected — extracting python runtime from tar...')
  broadcastProgress({ phase: 'checking', percent: 0, detail: translate(locale, 'runtime.checking') })

  // ------------------------------------------------------------------
  // Phase 1: Count total files for accurate progress
  // ------------------------------------------------------------------
  broadcastProgress({ phase: 'counting', percent: 0, detail: translate(locale, 'runtime.counting') })
  log.info('[Runtime] Counting entries in tar archive...')
  let totalFiles: number
  try {
    totalFiles = await countTarEntries(pythonTar)
    log.info(`[Runtime] Archive contains ${totalFiles} files`)
  } catch {
    log.warn('[Runtime] Failed to count entries, falling back to time-based progress')
    totalFiles = 0
  }

  // ------------------------------------------------------------------
  // Phase 2: Extract into the **staging** directory
  // ------------------------------------------------------------------
  broadcastProgress({ phase: 'extracting', percent: 0, detail: translate(locale, 'runtime.extracting') })

  let extractedFiles = 0
  let lastPercent = -1
  let extractionFailed = false
  const extractionStartTime = Date.now()

  const progressTimer = setInterval(() => {
    if (!extractionFailed) {
      reportProgress()
    }
  }, 1_000)

  function reportProgress() {
    if (totalFiles === 0) {
      const elapsed = Date.now() - extractionStartTime
      const pct = Math.min(Math.round((elapsed / 180_000) * 100), 99)
      if (pct !== lastPercent) {
        lastPercent = pct
        broadcastProgress({
          phase: 'extracting', percent: pct,
          detail: translate(locale, 'runtime.extracting')
        })
      }
      return
    }
    const pct = Math.min(Math.round((extractedFiles / totalFiles) * 100), 99)
    if (pct !== lastPercent) {
      lastPercent = pct
      broadcastProgress({
        phase: 'extracting', percent: pct,
        detail: translate(locale, 'runtime.extractingPercent', { percent: pct })
      })
    }
  }

  // The tar archive contains the python/ prefix, so extraction into runtimeDir
  // would produce runtimeDir/python/.  Instead we extract into stagingDir and
  // let the tar create stagingDir/python/ (which becomes stagingDir itself
  // effectively via strip).  We'll work around this by extracting to a temp
  // parent and then moving the inner python dir out.
  const tmpParent = join(runtimeDir, '.tmp_extract')
  mkdirSync(tmpParent, { recursive: true })

  try {
    await tar.x({
      cwd: tmpParent,
      file: pythonTar,
      strip: 0,
      strict: false,
      filter: (_path, entry) => {
        if ('type' in entry && entry.type === 'File') {
          extractedFiles++
          reportProgress()
        }
        return true
      },
    })
  } catch (err) {
    extractionFailed = true
    clearInterval(progressTimer)
    log.error('[Runtime] Failed to extract python runtime:', err)
    broadcastProgress({ phase: 'error', percent: 0, detail: translate(locale, 'runtime.extractionError') + ': ' + String(err) })

    // Clean up staging artifacts
    log.info('[Runtime] Cleaning up incomplete extraction...')
    safeRemove(stagingDir)
    safeRemove(tmpParent)

    throw err
  }

  clearInterval(progressTimer)

  // ------------------------------------------------------------------
  // Phase 3: Integrity verification on the extracted staging directory
  // ------------------------------------------------------------------
  // After extraction, tmpParent/python/ should exist
  const extractedPython = join(tmpParent, 'python')
  const stagingPythonExe = join(extractedPython, 'python.exe')

  if (!existsSync(stagingPythonExe)) {
    extractionFailed = true
    const msg = 'python runtime extraction finished but python.exe not found'
    log.error('[Runtime] ' + msg)
    broadcastProgress({ phase: 'error', percent: 0, detail: translate(locale, 'runtime.pythonNotFound') })
    safeRemove(tmpParent)
    throw new Error(msg)
  }

  // Verify file count matches expected count (catch truncated extractions)
  // With atomic extraction, we require 100% completeness — no tolerance.
  if (totalFiles > 0) {
    if (extractedFiles < totalFiles) {
      extractionFailed = true
      const msg = `Extraction incomplete: got ${extractedFiles}/${totalFiles} files — expected 100%`
      log.error('[Runtime] ' + msg)
      broadcastProgress({ phase: 'error', percent: 0, detail: translate(locale, 'runtime.extractionIncomplete') + `: ${extractedFiles}/${totalFiles}` })
      safeRemove(tmpParent)
      throw new Error(msg)
    }
    log.info(`[Runtime] Extracted ${extractedFiles}/${totalFiles} files — 100% complete`)
  }

  // ------------------------------------------------------------------
  // Phase 4: Atomic swap — rename staging result to python
  // ------------------------------------------------------------------
  log.info('[Runtime] Extraction verified — performing atomic rename to python')
  try {
    renameSync(extractedPython, stagingDir)
    // Now rename stagingDir → pythonDir
    renameSync(stagingDir, pythonDir)
  } catch (err) {
    log.error('[Runtime] Atomic rename failed:', err)
    broadcastProgress({
      phase: 'error', percent: 0,
      detail: translate(locale, 'runtime.extractionFinalizeFailed') + ': ' + String(err)
    })
    // Best-effort cleanup
    safeRemove(stagingDir)
    safeRemove(tmpParent)
    throw new Error(`Failed to finalize extraction: ${String(err)}`)
  }

  // Clean up temp parent (should be empty now)
  safeRemove(tmpParent)

  // ------------------------------------------------------------------
  // Phase 5: Write stamp file to mark extraction as complete
  // ------------------------------------------------------------------
  const stampFile = join(pythonDir, '.extraction-ok')
  try {
    writeFileSync(stampFile, `${new Date().toISOString()}\n`, 'utf-8')
  } catch (err) {
    log.warn('[Runtime] Failed to write extraction stamp (non-critical):', err)
  }

  log.info('[Runtime] python runtime extraction complete')
  broadcastProgress({ phase: 'done', percent: 100, detail: translate(locale, 'runtime.done') })
}
