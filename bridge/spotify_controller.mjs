/**
 * Deep Spotify & Media Controller for J.A.R.V.I.S.
 * 
 * Provides direct track searching, playback automation, and Windows virtual media keys.
 */

import { exec } from 'node:child_process'
import process from 'node:process'

/**
 * Execute native Windows Virtual Key command
 */
export function sendMediaKey(vkCode) {
  if (process.platform !== 'win32') return
  // 179 = Play/Pause, 176 = Next Track, 177 = Prev Track, 175 = Volume Up, 174 = Volume Down, 173 = Mute
  exec(`powershell -NoProfile -Command "$w = New-Object -ComObject Wscript.Shell; $w.SendKeys([char]${vkCode})"`, (err) => {
    if (err) console.warn('[jarvis:media] media key error:', err.message)
  })
}

/**
 * Controls media playback (play_pause, next, previous, volume)
 */
export function controlMedia(action) {
  const act = action.toLowerCase().trim()
  console.log(`[jarvis:media] action: ${act}`)

  switch (act) {
    case 'play_pause':
    case 'toggle':
    case 'pause':
    case 'play':
    case 'resume':
      sendMediaKey(179) // VK_MEDIA_PLAY_PAUSE
      break
    case 'next':
    case 'skip':
      sendMediaKey(176) // VK_MEDIA_NEXT_TRACK
      break
    case 'previous':
    case 'prev':
      sendMediaKey(177) // VK_MEDIA_PREV_TRACK
      break
    case 'volume_up':
      // Press 3 times for a noticeable step
      sendMediaKey(175)
      sendMediaKey(175)
      sendMediaKey(175)
      break
    case 'volume_down':
      sendMediaKey(174)
      sendMediaKey(174)
      sendMediaKey(174)
      break
    case 'mute':
      sendMediaKey(173) // VK_VOLUME_MUTE
      break
    default:
      console.warn(`[jarvis:media] unknown media action: ${action}`)
  }
}

/**
 * Plays a track or playlist on Spotify or YouTube
 */
export function playMusic(query, platform = 'spotify') {
  if (!query || typeof query !== 'string') return
  const clean = query.trim()

  if (platform.toLowerCase() === 'youtube') {
    const url = `https://www.youtube.com/results?search_query=${encodeURIComponent(clean)}`
    console.log(`[jarvis:media] launching YouTube search: "${clean}"`)
    if (process.platform === 'win32') {
      exec(`start "" "${url}"`, { shell: 'cmd.exe' })
    } else {
      exec(`open "${url}"`)
    }
    return
  }

  // Spotify URI search
  const spotifyUri = `spotify:search:${encodeURIComponent(clean)}`
  console.log(`[jarvis:media] launching Spotify: "${clean}" -> ${spotifyUri}`)

  if (process.platform === 'win32') {
    exec(`start "" "${spotifyUri}"`, { shell: 'cmd.exe' }, () => {
      // Small pause for Spotify window to gain focus, then send Enter/Play
      setTimeout(() => {
        exec('powershell -NoProfile -Command "$w = New-Object -ComObject Wscript.Shell; Start-Sleep -Milliseconds 600; $w.SendKeys(\'~{ENTER}\')"', () => {})
      }, 500)
    })
  } else if (process.platform === 'darwin') {
    exec(`open "${spotifyUri}"`)
  } else {
    exec(`xdg-open "${spotifyUri}"`)
  }
}
