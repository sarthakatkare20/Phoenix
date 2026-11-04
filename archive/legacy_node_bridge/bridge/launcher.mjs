import { exec } from 'node:child_process'
import process from 'node:process'

const APP_MAP = {
  spotify: 'spotify:',
  youtube: 'https://youtube.com',
  whatsapp: 'whatsapp:',
  discord: 'discord:',
  telegram: 'tg:',
  chrome: 'chrome',
  browser: 'https://google.com',
  google: 'https://google.com',
  notepad: 'notepad',
  calculator: 'calc',
  calc: 'calc',
  vscode: 'code',
  code: 'code',
  'vs code': 'code',
  terminal: 'cmd',
  cmd: 'cmd',
  powershell: 'powershell',
  explorer: 'explorer',
  files: 'explorer',
  settings: 'ms-settings:',
  camera: 'microsoft.windows.camera:',
  mail: 'outlookmail:',
  netflix: 'https://netflix.com',
  github: 'https://github.com',
  twitter: 'https://x.com',
  x: 'https://x.com',
  instagram: 'https://instagram.com',
  reddit: 'https://reddit.com',
}

/**
 * Open an app or website on Windows/Mac/Linux.
 */
export function launchTarget(rawTarget) {
  if (!rawTarget || typeof rawTarget !== 'string') return
  const clean = rawTarget
    .toLowerCase()
    .trim()
    .replace(/^(\[open:\s*|open\s+|launch\s+|start\s+)/i, '')
    .replace(/\]$/, '')
    .replace(/^(the|a|an)\s+/i, '')
    .trim()

  if (!clean) return

  const destination =
    APP_MAP[clean] ||
    (clean.startsWith('http://') || clean.startsWith('https://')
      ? clean
      : clean.includes('.com') || clean.includes('.org') || clean.includes('.io') || clean.includes('.net')
        ? `https://${clean}`
        : clean)

  console.log(`[jarvis:launcher] opening "${clean}" -> "${destination}"`)

  if (process.platform === 'win32') {
    // Using start in cmd.exe handles URL schemes, protocol handlers, and executables cleanly
    exec(`start "" "${destination}"`, { shell: 'cmd.exe' }, (err) => {
      if (err) {
        // Fallback without quotes if it was a bare executable
        exec(`start ${destination}`, { shell: 'cmd.exe' }, () => {})
      }
    })
  } else if (process.platform === 'darwin') {
    exec(`open "${destination}"`)
  } else {
    exec(`xdg-open "${destination}"`)
  }
}

/**
 * Detects if a user message is asking to open an app or site.
 */
export function detectAppLaunchIntent(text) {
  if (!text || typeof text !== 'string') return null
  const t = text.trim()
  
  // English: "open spotify", "launch chrome", "please open youtube"
  const enMatch = t.match(/^(?:please\s+)?(?:open|launch|start|run|play)\s+([a-zA-Z0-9_\-.\s]+)$/i)
  if (enMatch && enMatch[1]) {
    const target = enMatch[1].trim()
    // Ignore non-app phrases like "open minded", "open the door"
    if (!['minded', 'door', 'window', 'eyes', 'mouth'].includes(target.toLowerCase())) {
      return target
    }
  }

  // Hindi/Hinglish: "spotify kholo", "youtube open karo", "notepad chalao"
  const hiMatch = t.match(/^([a-zA-Z0-9_\-.\s]+)\s+(?:kholo|khol do|open karo|chalao|start karo)$/i)
  if (hiMatch && hiMatch[1]) {
    return hiMatch[1].trim()
  }

  return null
}
