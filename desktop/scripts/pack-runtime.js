/**
 * Build-time script: cleans unnecessary files from runtime/python and packs
 * it into a single .tar archive (no compression).
 *
 * Removes: __pycache__, .pyc, .pyi, tests/, .chm, dist-info/RECORD, etc.
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

function main() {
  if (!fs.existsSync(pythonDir)) {
    console.error('Error: runtime/python not found at', pythonDir)
    process.exit(1)
  }

  // Step 1: Clean unnecessary files
  console.log('[pack-runtime] Cleaning unnecessary files (.pyc, .pyi, tests/, .chm, RECORD, ...)...')
  const { removedDirs, removedFiles } = cleanPythonDir(pythonDir)
  console.log(`[pack-runtime] Removed ${removedDirs} dirs, ${removedFiles} files`)

  // Step 2: Remove old archive
  if (fs.existsSync(outputFile)) {
    fs.unlinkSync(outputFile)
  }

  // Step 3: Create tar archive (no compression — fast streaming format)
  console.log('[pack-runtime] Creating tar archive (no compression)...')

  tar.c(
    {
      cwd: runtimeDir,
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
    })
}

main()
