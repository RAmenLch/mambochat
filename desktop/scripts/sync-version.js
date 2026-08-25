/**
 * Build-time script: syncs the app version from frontend/mambo/package.json
 * (the single source of truth for the frontend) into desktop/package.json and
 * desktop/package-lock.json root entries, so the desktop release version
 * (installer / portable artifact names) always follows the frontend version.
 *
 * Usage: node scripts/sync-version.js
 */

const fs = require('fs')
const path = require('path')

const projectRoot = path.resolve(__dirname, '..', '..')
const frontendPkgPath = path.join(projectRoot, 'frontend', 'mambo', 'package.json')
const desktopPkgPath = path.join(__dirname, '..', 'package.json')
const desktopLockPath = path.join(__dirname, '..', 'package-lock.json')

const frontendPkg = JSON.parse(fs.readFileSync(frontendPkgPath, 'utf-8'))
const version = frontendPkg.version

const desktopPkg = JSON.parse(fs.readFileSync(desktopPkgPath, 'utf-8'))
desktopPkg.version = version
fs.writeFileSync(desktopPkgPath, JSON.stringify(desktopPkg, null, 2) + '\n')

if (fs.existsSync(desktopLockPath)) {
  const lock = JSON.parse(fs.readFileSync(desktopLockPath, 'utf-8'))
  lock.version = version
  if (lock.packages && lock.packages['']) {
    lock.packages[''].version = version
  }
  fs.writeFileSync(desktopLockPath, JSON.stringify(lock, null, 2) + '\n')
}

console.log(`[sync-version] desktop version synced -> ${version}`)
