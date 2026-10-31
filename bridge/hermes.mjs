/**
 * Hermes / Ollama Bridge Provider for J.A.R.V.I.S.
 *
 * Runs locally via Ollama.
 * Streams token deltas and conversation turns over WebSocket to the JARVIS frontend.
 * Full OS Control: App launching, Antigravity IDE, window minimize/restore, file & folder creation.
 */

import { executeAction, detectSystemIntent, launchTarget } from './system_control.mjs'
import { ConversationSession } from './conversation_manager.mjs'

const OLLAMA_URL =
  process.env.HERMES_URL || process.env.OLLAMA_URL || 'http://localhost:11434'
const HERMES_MODEL =
  process.env.HERMES_MODEL || process.env.JARVIS_MODEL || 'hermes3:latest'

export function createHermesHandler({
  systemPrompt,
  mcpServers = {},
}) {
  const enhancedSystemPrompt = `${systemPrompt}

FULL SYSTEM & OS CONTROL:
You are JARVIS with direct control over this computer.
You can launch apps, play music on Spotify or YouTube, control playback, control windows, search Google, and create files:
1. Play music on Spotify or YouTube (e.g. "play Hola Amigo", "play Starboy on Spotify", "open Spotify and play Hola Amigo"):
   Use action tag: [ACTION: {"type": "play_music", "query": "Hola Amigo", "platform": "spotify"}]
2. Media playback control (Play/Pause, Next song, Previous song):
   Use action tag: [ACTION: {"type": "media", "action": "play_pause"}] or [ACTION: {"type": "media", "action": "next"}]
3. Search Google / Web:
   Use action tag: [ACTION: {"type": "search", "query": "latest AI news"}]
4. Open apps / websites (e.g. Antigravity, Spotify, YouTube, Chrome, Notepad, Calculator, VS Code, WhatsApp, Discord):
   Use action tag: [ACTION: {"type": "open", "target": "antigravity"}]
5. Minimize all windows / Show desktop:
   Use action tag: [ACTION: {"type": "minimize"}]
6. Restore / Unminimize windows:
   Use action tag: [ACTION: {"type": "restore"}]
7. Create a file with content on disk:
   Use action tag: [ACTION: {"type": "create_file", "name": "filename.txt", "content": "file content here"}]
8. Create a new folder on disk:
   Use action tag: [ACTION: {"type": "create_folder", "name": "folder_name"}]
9. Volume control:
   Use action tags: [ACTION: {"type": "volume_up"}], [ACTION: {"type": "volume_down"}], [ACTION: {"type": "mute"}]
10. Lock PC:
   Use action tag: [ACTION: {"type": "lock"}]

Always confirm the action in your crisp, sophisticated spoken response (e.g. "Playing Hola Amigo on Spotify for you, sir.", "Opening Antigravity IDE, sir.", "Minimizing windows, sir.").`

  return function handleHermesConnection(socket) {
    console.log(`[jarvis:hermes] client connected (using model ${HERMES_MODEL} at ${OLLAMA_URL})`)
    const convSession = new ConversationSession(null, `hermes (${HERMES_MODEL})`)

    // Notify HUD that Hermes & System Control are ready
    const serverList = [
      'hermes3 (local)',
      'ollama',
      'system-control (windows)',
      'file-engine (local)',
      ...Object.keys(mcpServers),
    ]
    if (socket.readyState === socket.OPEN) {
      socket.send(JSON.stringify({ type: 'ready', servers: serverList }))
    }

    const messages = [{ role: 'system', content: enhancedSystemPrompt }]
    let currentAbort = null
    let answering = null

    const send = (msg) => {
      if (socket.readyState === socket.OPEN) {
        socket.send(JSON.stringify(msg))
      }
    }

    const sendTurn = (msg) => send({ ...msg, ask: answering })

    async function handleAsk(text, id) {
      if (currentAbort) {
        currentAbort.abort()
        currentAbort = null
      }

      answering = id
      convSession.addUserMessage(text)

      // Direct intent detection for instant execution
      const directIntent = detectSystemIntent(text)
      if (directIntent) {
        sendTurn({ type: 'tool', name: `system · ${directIntent.type || 'action'}` })
        executeAction(directIntent)
      }

      messages.push({ role: 'user', content: text })

      // Keep context manageable (last 25 messages)
      if (messages.length > 25) {
        messages.splice(1, messages.length - 21)
      }

      const abortController = new AbortController()
      currentAbort = abortController

      let fullAssistantText = ''
      let executedFromModel = Boolean(directIntent)

      try {
        const response = await fetch(`${OLLAMA_URL}/api/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: HERMES_MODEL,
            messages,
            stream: true,
            options: {
              temperature: 0.65,
              top_p: 0.9,
              num_ctx: 16384,
              repeat_penalty: 1.1,
            },
          }),
          signal: abortController.signal,
        })

        if (!response.ok) {
          const errText = await response.text()
          throw new Error(`Ollama error (${response.status}): ${errText}`)
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let streamBuffer = ''

        while (true) {
          const { value, done } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''

          for (const line of lines) {
            if (!line.trim()) continue
            try {
              const chunk = JSON.parse(line)
              const token = chunk.message?.content
              if (token) {
                fullAssistantText += token
                streamBuffer += token

                // Check for [ACTION: ...] or [OPEN: ...] tags
                const actionMatch = streamBuffer.match(/\[ACTION:\s*({[^\]]+})\]/i)
                if (actionMatch && actionMatch[1]) {
                  if (!executedFromModel) {
                    try {
                      const actionObj = JSON.parse(actionMatch[1])
                      sendTurn({ type: 'tool', name: `system · ${actionObj.type || 'action'}` })
                      executeAction(actionObj)
                      executedFromModel = true
                    } catch {
                      // ignore parse error in stream chunk
                    }
                  }
                  streamBuffer = streamBuffer.replace(/\[ACTION:\s*{[^\]]+}\]/gi, '')
                }

                const openMatch = streamBuffer.match(/\[OPEN:\s*([^\]]+)\]/i)
                if (openMatch && openMatch[1]) {
                  if (!executedFromModel) {
                    sendTurn({ type: 'tool', name: `launch · ${openMatch[1]}` })
                    launchTarget(openMatch[1])
                    executedFromModel = true
                  }
                  streamBuffer = streamBuffer.replace(/\[OPEN:\s*[^\]]+\]/gi, '')
                }

                // If not in the middle of a bracket tag, stream the delta
                if (!streamBuffer.includes('[')) {
                  if (streamBuffer.length > 0) {
                    sendTurn({ type: 'text', delta: streamBuffer })
                    streamBuffer = ''
                  }
                }
              }
              if (chunk.done) {
                break
              }
            } catch {
              // Ignore line parse error in stream chunk
            }
          }
        }

        // Flush any remaining tokens without bracket tags
        if (streamBuffer) {
          const cleanRemaining = streamBuffer
            .replace(/\[ACTION:\s*{[^\]]+}\]/gi, '')
            .replace(/\[OPEN:\s*[^\]]+\]/gi, '')
            .trim()
          if (cleanRemaining) {
            sendTurn({ type: 'text', delta: cleanRemaining })
          }
        }

        const cleanAssistantText = fullAssistantText
          .replace(/\[ACTION:\s*{[^\]]+}\]/gi, '')
          .replace(/\[OPEN:\s*[^\]]+\]/gi, '')
          .trim()

        if (cleanAssistantText) {
          messages.push({ role: 'assistant', content: cleanAssistantText })
          convSession.addAssistantMessage(cleanAssistantText)
        }

        sendTurn({
          type: 'done',
          text: cleanAssistantText,
          costUsd: 0,
        })
      } catch (err) {
        if (err.name === 'AbortError') {
          return
        }
        console.error('[jarvis:hermes] chat error:', err)
        sendTurn({
          type: 'error',
          message: `Local LLM error: ${err.message}`,
        })
      } finally {
        if (currentAbort === abortController) {
          currentAbort = null
        }
      }
    }

    socket.on('message', (raw) => {
      let msg
      try {
        msg = JSON.parse(raw.toString())
      } catch {
        return
      }

      if (msg.type === 'ask' && typeof msg.text === 'string') {
        const text = msg.text
        const id = typeof msg.id === 'string' ? msg.id : null
        handleAsk(text, id)
      }

      if (msg.type === 'interrupt') {
        if (currentAbort) {
          currentAbort.abort()
          currentAbort = null
        }
      }
    })

    socket.on('close', () => {
      console.log('[jarvis:hermes] client disconnected')
      if (currentAbort) {
        currentAbort.abort()
        currentAbort = null
      }
    })
  }
}
