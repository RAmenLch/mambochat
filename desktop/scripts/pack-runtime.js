/**
 * Build-time script: packs the Python runtime into a single .tar archive
 * (no compression) for the desktop app.
 *
 * Works on a TEMPORARY COPY of runtime/python so the development runtime is
 * never mutated. The copy is sanitized before packing:
 *  - removes __pycache__, .pyc, .pyi, tests/, .chm, dist-info/RECORD, etc.
 *  - removes console-script launchers (*.exe + shebang text scripts) whose
 *    embedded shebang hard-codes the build machine's absolute Python path
 *  - removes editable-install artifacts (__editable__*.pth / *_finder.py /
 *    dist-info/direct_url.json) that leak build-machine source paths
 *  - writes mambo-backend.pth (relative import path) and Scripts/mambo.cmd
 *    so the mambo CLI works self-contained on end-user machines
 *
 * Usage: node scripts/pack-runtime.js
 */

const fs = require('fs')
const path = require('path')
const tar = require('tar')

const projectRoot = path.resolve(__dirname, '..', '..')
const runtimeDir = path.join(projectRoot, 'runtime')
const pythonDir = path.join(runtimeDir, 'python')
const outputFile = path.join(runtimeDir, 'python.tar')
const stagingRoot = path.join(runtimeDir, '.python-pack-tmp')
const stagingDir = path.join(stagingRoot, 'python')

// Directory names to skip entirely (recursively deleted)
const EXCLUDE_DIRS = new Set([
  '__pycache__',
  'tests',
  'test',
  '__tests__',
  'Demos',
  'HTML',
])

// File patterns to remove
const EXCLUDE_FILE = [
  /\.pyc$/,
  /\.pyo$/,
  /\.pyi$/,
  /\.chm$/,
  /RECORD$/,         // dist-info/RECORD (pip install manifest, not needed at runtime)
  /conftest\.py$/,
  /test_.*\.py$/,
  /.*_test\.py$/,
]

function shouldExcludeFile(name) {
  return EXCLUDE_FILE.some(re => re.test(name))
}

/**
 * Recursively remove unnecessary directories and files.
 */
function cleanPythonDir(dir) {
  let removedDirs = 0
  let removedFiles = 0

  const entries = fs.readdirSync(dir, { withFileTypes: true })
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (EXCLUDE_DIRS.has(entry.name)) {
        fs.rmSync(fullPath, { recursive: true, force: true })
        removedDirs++
      } else {
        const sub = cleanPythonDir(fullPath)
        removedDirs += sub.removedDirs
        removedFiles += sub.removedFiles
      }
    } else if (shouldExcludeFile(entry.name)) {
      fs.unlinkSync(fullPath)
      removedFiles++
    }
  }
  return { removedDirs, removedFiles }
}

/**
 * Remove console-script launchers whose embedded shebang hard-codes the
 * build machine's Python path (privacy leak; also broken on user machines).
 * Covers *.exe launchers and text scripts with a leading shebang line.
 */
function removeLaunchers(dir) {
  const scriptsDir = path.join(dir, 'Scripts')
  if (!fs.existsSync(scriptsDir)) return 0

  let removed = 0
  for (const name of fs.readdirSync(scriptsDir)) {
    const fullPath = path.join(scriptsDir, name)
    if (!fs.statSync(fullPath).isFile()) continue
    if (name.endsWith('.exe')) {
      fs.unlinkSync(fullPath)
      removed++
      continue
    }
    try {
      const firstLine = fs.readFileSync(fullPath, 'utf8').split(/\r?\n/, 1)[0] || ''
      if (firstLine.startsWith('#!')) {
        fs.unlinkSync(fullPath)
        removed++
      }
    } catch {
      // binary/unreadable — keep
    }
  }
  return removed
}

/**
 * Remove editable-install artifacts that hard-code build-machine source paths:
 * __editable__*.pth, __editable___*_finder.py and *.dist-info/direct_url.json.
 */
function removeEditableArtifacts(sitePackagesDir) {
  let removed = 0
  for (const name of fs.readdirSync(sitePackagesDir)) {
    if (name.startsWith('__editable__')) {
      fs.unlinkSync(path.join(sitePackagesDir, name))
      removed++
    }
  }
  for (const name of fs.readdirSync(sitePackagesDir)) {
    if (!name.endsWith('.dist-info')) continue
    const directUrl = path.join(sitePackagesDir, name, 'direct_url.json')
    if (fs.existsSync(directUrl)) {
      fs.unlinkSync(directUrl)
      removed++
    }
  }
  return removed
}

function main() {
  if (!fs.existsSync(pythonDir)) {
    console.error('Error: runtime/python not found at', pythonDir)
    process.exit(1)
  }

  // Step 0: copy runtime/python to a staging dir (never mutate the dev runtime)
  console.log('[pack-runtime] Copying runtime/python to staging...')
  fs.rmSync(stagingRoot, { recursive: true, force: true })
  fs.cpSync(pythonDir, stagingDir, { recursive: true })

  // Step 1: Clean unnecessary files
  console.log('[pack-runtime] Cleaning unnecessary files (.pyc, .pyi, tests/, .chm, RECORD, ...)...')
  const { removedDirs, removedFiles } = cleanPythonDir(stagingDir)
  console.log(`[pack-runtime] Removed ${removedDirs} dirs, ${removedFiles} files`)

  // Step 2: Sanitize launchers & editable artifacts (privacy / portability)
  const removedLaunchers = removeLaunchers(stagingDir)
  const sitePackagesDir = path.join(stagingDir, 'Lib', 'site-packages')
  const removedEditable = removeEditableArtifacts(sitePackagesDir)
  console.log(`[pack-runtime] Removed ${removedLaunchers} launchers, ${removedEditable} editable artifacts`)

  // Step 3: Self-contained mambo CLI
  // - mambo-backend.pth: relative path (site-packages -> 4 levels up = resources/)
  //   lets `python -m backend.mambo_cli` import the shipped backend package.
  // - Scripts/mambo.cmd: absolute-position launcher, no shebang dependency.
  fs.writeFileSync(path.join(sitePackagesDir, 'mambo-backend.pth'), '../../../..\n', 'utf-8')
  fs.writeFileSync(
    path.join(stagingDir, 'Scripts', 'mambo.cmd'),
    '@echo off\r\n"%~dp0..\\python.exe" -m backend.mambo_cli %*\r\n',
    'utf-8'
  )
  console.log('[pack-runtime] Wrote mambo-backend.pth + Scripts/mambo.cmd')

  // Step 4: Remove old archive
  if (fs.existsSync(outputFile)) {
    fs.unlinkSync(outputFile)
  }

  // Step 5: Create tar archive (no compression — fast streaming format)
  console.log('[pack-runtime] Creating tar archive (no compression)...')
  tar.c(
    {
      cwd: stagingRoot,
      gzip: false,
      portable: true,
    },
    ['python'],
  )
    .pipe(fs.createWriteStream(outputFile))
    .on('finish', () => {
      const stat = fs.statSync(outputFile)
      const sizeMB = (stat.size / 1024 / 1024).toFixed(1)
      console.log(`[pack-runtime] Created python.tar: ${sizeMB} MB`)
      fs.rmSync(stagingRoot, { recursive: true, force: true })
      console.log('[pack-runtime] Staging dir cleaned up')
    })
}

main()
