/**
 * System Control & File Automation Engine for J.A.R.V.I.S.
 *
 * Provides OS-level actions on Windows:
 * - Launching apps (Antigravity, Spotify, VS Code, Chrome, etc.)
 * - Window controls (Minimize all, Restore, Show desktop, Lock)
 * - Volume control (Volume up, Volume down, Mute)
 * - File and directory operations (Create file, write content, make folder, delete)
 * - Running shell commands
 */

import { exec } from 'node:child_process'
import { writeFileSync, mkdirSync, existsSync } from 'node:fs'
import os, { homedir } from 'node:os'
import { join, isAbsolute } from 'node:path'
import process from 'node:process'

// Locate user-specific programs
const USER_HOME = homedir()
const LOCAL_APP_DATA = process.env.LOCALAPPDATA || join(USER_HOME, 'AppData', 'Local')

const ANTIGRAVITY_PATH = existsSync(join(LOCAL_APP_DATA, 'Programs', 'antigravity', 'Antigravity.exe'))
  ? join(LOCAL_APP_DATA, 'Programs', 'antigravity', 'Antigravity.exe')
  : existsSync(join(LOCAL_APP_DATA, 'Programs', 'Antigravity IDE', 'Antigravity IDE.exe'))
    ? join(LOCAL_APP_DATA, 'Programs', 'Antigravity IDE', 'Antigravity IDE.exe')
    : 'antigravity'

export const APP_MAP = {
  antigravity: ANTIGRAVITY_PATH,
  'antigravity ide': ANTIGRAVITY_PATH,
  agy: ANTIGRAVITY_PATH,
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
 * Open an app or website.
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

  console.log(`[jarvis:control] opening "${clean}" -> "${destination}"`)

  if (process.platform === 'win32') {
    if (destination.endsWith('.exe')) {
      exec(`start "" "${destination}"`, { shell: 'cmd.exe' })
    } else {
      exec(`start "" "${destination}"`, { shell: 'cmd.exe' }, (err) => {
        if (err) {
          exec(`start ${destination}`, { shell: 'cmd.exe' }, () => {})
        }
      })
    }
  } else if (process.platform === 'darwin') {
    exec(`open "${destination}"`)
  } else {
    exec(`xdg-open "${destination}"`)
  }
}

/**
 * Window & System Controls
 */
export function minimizeAll() {
  console.log('[jarvis:control] minimizing all windows')
  if (process.platform === 'win32') {
    exec('powershell -command "(New-Object -ComObject Shell.Application).MinimizeAll()"')
  }
}

export function restoreAll() {
  console.log('[jarvis:control] restoring all windows')
  if (process.platform === 'win32') {
    exec('powershell -command "(New-Object -ComObject Shell.Application).UndoMinimizeAll()"')
  }
}

export function lockWorkstation() {
  console.log('[jarvis:control] locking computer')
  if (process.platform === 'win32') {
    exec('rundll32.exe user32.dll,LockWorkStation')
  }
}

export function changeVolume(direction) {
  console.log(`[jarvis:control] volume ${direction}`)
  if (process.platform === 'win32') {
    const key = direction === 'up' ? 175 : direction === 'down' ? 174 : 173 // 173 = mute
    exec(`powershell -command "$w = New-Object -ComObject WScript.Shell; for($i=0;$i<5;$i++){ $w.SendKeys([char]${key}) }"`)
  }
}

/**
 * File & Folder Creation
 */
export function createFileSystemItem({ type = 'file', name, content = '', targetPath = '' }) {
  try {
    const basePath = targetPath
      ? isAbsolute(targetPath)
        ? targetPath
        : join(process.cwd(), targetPath)
      : process.cwd()

    const fullPath = isAbsolute(name) ? name : join(basePath, name)

    if (type === 'folder' || type === 'directory') {
      mkdirSync(fullPath, { recursive: true })
      console.log(`[jarvis:control] created folder: ${fullPath}`)
      return { ok: true, path: fullPath }
    }

    writeFileSync(fullPath, content, 'utf8')
    console.log(`[jarvis:control] created file: ${fullPath}`)
    return { ok: true, path: fullPath }
  } catch (err) {
    console.error('[jarvis:control] file system error:', err.message)
    return { ok: false, error: err.message }
  }
}

/**
 * Media & Music Control
 */
export function playMusic(query, platform = 'spotify') {
  const cleanQuery = query ? query.trim() : ''
  console.log(`[jarvis:control] playing music: "${cleanQuery}" on ${platform}`)

  if (process.platform === 'win32') {
    if (platform === 'youtube' || (!cleanQuery && platform !== 'spotify')) {
      const url = cleanQuery
        ? `https://www.youtube.com/results?search_query=${encodeURIComponent(cleanQuery)}`
        : 'https://youtube.com'
      exec(`start "" "${url}"`, { shell: 'cmd.exe' })
    } else {
      // Open Spotify with song search
      const uri = cleanQuery ? `spotify:search:${encodeURIComponent(cleanQuery)}` : 'spotify:'
      exec(`start "" "${uri}"`, { shell: 'cmd.exe' }, (err) => {
        if (err) {
          const webUrl = cleanQuery
            ? `https://open.spotify.com/search/${encodeURIComponent(cleanQuery)}`
            : 'https://open.spotify.com'
          exec(`start "" "${webUrl}"`, { shell: 'cmd.exe' })
        }
      })
    }
  } else {
    launchTarget(platform === 'youtube' ? `https://www.youtube.com/results?search_query=${encodeURIComponent(cleanQuery)}` : 'spotify:')
  }
}

export function controlMedia(action) {
  console.log(`[jarvis:control] media action: ${action}`)
  if (process.platform === 'win32') {
    let key = 179 // 179 = Play/Pause
    if (action === 'next') key = 176
    else if (action === 'prev' || action === 'previous') key = 177
    else if (action === 'stop') key = 178

    exec(`powershell -command "$w = New-Object -ComObject WScript.Shell; $w.SendKeys([char]${key})"`)
  }
}

export function searchWeb(query) {
  const clean = encodeURIComponent(query.trim())
  console.log(`[jarvis:control] searching web for: "${query}"`)
  if (process.platform === 'win32') {
    exec(`start "" "https://www.google.com/search?q=${clean}"`, { shell: 'cmd.exe' })
  } else {
    launchTarget(`https://www.google.com/search?q=${clean}`)
  }
}

/**
 * Parses and executes actions from user prompts or model tags.
 */
export function executeAction(action) {
  if (!action || typeof action !== 'object') return
  switch (action.type) {
    case 'open':
    case 'launch':
      if (action.target) launchTarget(action.target)
      break
    case 'play_music':
    case 'spotify':
      playMusic(action.query || action.song || action.target || '', action.platform || 'spotify')
      break
    case 'media':
      controlMedia(action.action || 'play_pause')
      break
    case 'search':
      if (action.query) searchWeb(action.query)
      break
    case 'minimize':
    case 'minimize_all':
      minimizeAll()
      break
    case 'restore':
    case 'undo_minimize':
      restoreAll()
      break
    case 'lock':
    case 'lock_pc':
      lockWorkstation()
      break
    case 'volume_up':
      changeVolume('up')
      break
    case 'volume_down':
      changeVolume('down')
      break
    case 'mute':
      changeVolume('mute')
      break
    case 'create_file':
      createFileSystemItem({
        type: 'file',
        name: action.name || action.path || 'untitled.txt',
        content: action.content || '',
      })
      break
    case 'create_folder':
      createFileSystemItem({
        type: 'folder',
        name: action.name || action.path || 'New Folder',
      })
      break
  }
}

/**
 * Fast direct intent matching for common system, music & file commands.
 */
export function detectSystemIntent(text) {
  if (!text || typeof text !== 'string') return null
  const t = text.trim().toLowerCase()

  // 1. Music - Spotify & YouTube (e.g. "open spotify and play hola amigo", "play hola amigo on spotify", "spotify pe hola amigo chalao", "play starboy")
  const spotifyPlayMatch =
    t.match(/(?:open\s+spotify\s+and\s+play|play\s+on\s+spotify|play\s+(.*?)\s+on\s+spotify|spotify\s+(?:pe|par)\s+(.*?)\s+(?:chalao|bajao|play karo)|play\s+spotify\s+(.*))/i) ||
    t.match(/^(?:play|chalao|bajao)\s+(.*?)(?:\s+(?:on|in)\s+spotify)?$/i)
  if (spotifyPlayMatch) {
    const rawSong = spotifyPlayMatch[1] || spotifyPlayMatch[2] || spotifyPlayMatch[3] || ''
    const song = rawSong
      .replace(/^song\s+/i, '')
      .replace(/^music\s+/i, '')
      .replace(/^track\s+/i, '')
      .replace(/\s+(?:on|in)\s+spotify$/i, '')
      .trim()
    if (song && !['music', 'song', 'gaana', 'something'].includes(song)) {
      return { type: 'play_music', query: song, platform: 'spotify' }
    } else if (t.includes('spotify')) {
      return { type: 'open', target: 'spotify' }
    }
  }

  // 2. YouTube Play (e.g. "play <song> on youtube", "youtube pe <song> chalao")
  const ytMatch = t.match(/(?:play\s+(.*?)\s+on\s+youtube|youtube\s+(?:pe|par)\s+(.*?)\s+(?:chalao|bajao|play karo))/i)
  if (ytMatch) {
    const song = (ytMatch[1] || ytMatch[2] || '').trim()
    return { type: 'play_music', query: song, platform: 'youtube' }
  }

  // 3. Media Controls (Play / Pause / Next / Prev)
  if (/\b(pause music|pause song|stop music|gaana roko|pause karo|pause)\b/i.test(t)) {
    return { type: 'media', action: 'play_pause' }
  }
  if (/\b(resume music|play music|unpause|gaana chalao|continue music)\b/i.test(t) && !t.includes('play ')) {
    return { type: 'media', action: 'play_pause' }
  }
  if (/\b(next song|next track|agla gaana|change song|skip song|skip)\b/i.test(t)) {
    return { type: 'media', action: 'next' }
  }
  if (/\b(previous song|prev song|pichhla gaana|last song)\b/i.test(t)) {
    return { type: 'media', action: 'prev' }
  }

  // 4. Web Search (e.g. "search <query> on google", "google search <query>")
  const searchMatch = t.match(/(?:search\s+(?:for\s+)?(.*?)\s+on\s+google|google\s+(?:search|pe search karo)\s+(.*))/i)
  if (searchMatch) {
    const query = (searchMatch[1] || searchMatch[2] || '').trim()
    if (query) return { type: 'search', query }
  }

  // 5. Window Minimize / Restore
  if (/\b(minimize|chhota karo|screen chupa do|hide windows|show desktop)\b/i.test(t)) {
    return { type: 'minimize' }
  }
  if (/\b(restore|unminimize|bada karo|show windows|wapas lao)\b/i.test(t)) {
    return { type: 'restore' }
  }

  // 6. Lock PC
  if (/\b(lock|lock pc|computer lock karo|lock screen)\b/i.test(t)) {
    return { type: 'lock' }
  }

  // 7. Volume
  if (/\b(volume up|aawaz badhao|aawaz tez karo|loud|louder)\b/i.test(t)) {
    return { type: 'volume_up' }
  }
  if (/\b(volume down|aawaz kam karo|dheemi karo|quieter)\b/i.test(t)) {
    return { type: 'volume_down' }
  }
  if (/\b(mute|unmute|chup|silent)\b/i.test(t)) {
    return { type: 'mute' }
  }

  // 8. Create file
  const fileMatch = text.match(/(?:create|make|banao)\s+(?:a\s+)?file\s+(?:named\s+|called\s+)?([a-zA-Z0-9_\-.]+)(?:\s+(?:with|me|jisme)\s+(?:text|content|code)?\s*(.*))?/i)
  if (fileMatch) {
    return {
      type: 'create_file',
      name: fileMatch[1].trim(),
      content: fileMatch[2] ? fileMatch[2].trim() : '',
    }
  }

  // 9. Create folder
  const folderMatch = text.match(/(?:create|make|banao)\s+(?:a\s+)?folder\s+(?:named\s+|called\s+)?([a-zA-Z0-9_\-.]+)/i)
  if (folderMatch) {
    return {
      type: 'create_folder',
      name: folderMatch[1].trim(),
    }
  }

  // 10. App launch
  const enMatch = text.match(/^(?:please\s+)?(?:open|launch|start|run)\s+([a-zA-Z0-9_\-.\s]+)$/i)
  if (enMatch && enMatch[1]) {
    const target = enMatch[1].trim()
    if (!['minded', 'door', 'window', 'eyes', 'mouth'].includes(target.toLowerCase())) {
      return { type: 'open', target }
    }
  }

  const hiMatch = text.match(/^([a-zA-Z0-9_\-.\s]+)\s+(?:kholo|khol do|open karo|start karo)$/i)
  if (hiMatch && hiMatch[1]) {
    return { type: 'open', target: hiMatch[1].trim() }
  }

  // 11. System Status / Diagnostics Intent
  if (/\b(system status|diagnostics|diagnostics report|system stats|battery kitni hai|battery status|system report)\b/i.test(t)) {
    return { type: 'system_status' }
  }

  return null
}

let lastCpuTimes = null

export async function getSystemDiagnostics() {
  const cpus = os.cpus()
  let user = 0, nice = 0, sys = 0, idle = 0, irq = 0
  for (const cpu of cpus) {
    user += cpu.times.user
    nice += cpu.times.nice
    sys += cpu.times.sys
    idle += cpu.times.idle
    irq += cpu.times.irq
  }
  const total = user + nice + sys + idle + irq
  let cpuPercent = 18
  if (lastCpuTimes) {
    const idleDiff = idle - lastCpuTimes.idle
    const totalDiff = total - lastCpuTimes.total
    if (totalDiff > 0) {
      cpuPercent = Math.max(0, Math.min(100, Math.round((1 - idleDiff / totalDiff) * 100)))
    }
  }
  lastCpuTimes = { idle, total }

  const freeMem = os.freemem()
  const totalMem = os.totalmem()
  const usedMem = totalMem - freeMem
  const ramPercent = Math.round((usedMem / totalMem) * 100)

  let batteryPercent = null
  let isCharging = null

  if (process.platform === 'win32') {
    try {
      const batRaw = await new Promise((res) => {
        exec('powershell -NoProfile -Command "(Get-CimInstance Win32_Battery) | Select-Object -Property EstimatedChargeRemaining, BatteryStatus | ConvertTo-Json"', (err, stdout) => {
          if (err || !stdout) return res(null)
          try {
            res(JSON.parse(stdout))
          } catch {
            res(null)
          }
        })
      })
      if (batRaw) {
        batteryPercent = batRaw.EstimatedChargeRemaining ?? null
        const status = batRaw.BatteryStatus
        isCharging = status === 2 || status === 6 || status === 7 || status === 8 || status === 9 || status === 3
      }
    } catch {
      // ignore
    }
  }

  return {
    cpuPercent,
    ramPercent,
    ramUsedGb: (usedMem / (1024 ** 3)).toFixed(1),
    ramTotalGb: (totalMem / (1024 ** 3)).toFixed(1),
    uptimeMinutes: Math.round(os.uptime() / 60),
    batteryPercent,
    isCharging,
  }
}
