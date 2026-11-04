/**
 * Google Gemini Bridge Provider for J.A.R.V.I.S.
 *
 * Integrated with:
 * 1. Live Web Search (Weather, news, facts, current events)
 * 2. Deep Spotify & Media Automation (Virtual media keys, track search)
 * 3. Long-Term Memory & User Profile (Remembers user facts, name, preferences)
 */

import { executeAction, detectSystemIntent, launchTarget } from './system_control.mjs'
import { ConversationSession } from './conversation_manager.mjs'
import { liveWebSearch } from './web_search.mjs'
import { playMusic as playSpotifyMusic, controlMedia as controlSpotifyMedia } from './spotify_controller.mjs'
import { detectMemoryIntent, getMemoryContextPrompt } from './memory_manager.mjs'
import { readFileSync, existsSync } from 'node:fs'
import process from 'node:process'

function getGeminiKey() {
  if (process.env.GEMINI_API_KEY) return process.env.GEMINI_API_KEY
  if (process.env.GOOGLE_API_KEY) return process.env.GOOGLE_API_KEY
  if (existsSync('.env.local')) {
    try {
      const env = readFileSync('.env.local', 'utf8')
      const match = env.match(/(?:GEMINI_API_KEY|GOOGLE_API_KEY)=([^\r\n]+)/)
      if (match) return match[1].trim()
    } catch {
      // ignore
    }
  }
  return null
}

const CANDIDATE_MODELS = [
  'gemini-3.5-flash',
  'gemini-3.5-flash-lite',
  'gemini-3.8-flash',
  'gemini-flash-latest',
]

export function createGeminiHandler({ systemPrompt, mcpServers = {} }) {
  const baseSystemPrompt = `${systemPrompt}

FULL SYSTEM & OS CONTROL:
You are JARVIS with direct control over this Windows PC.
You can launch apps, play music on Spotify or YouTube, control playback, control windows, search Google, and create files:
1. Play music on Spotify or YouTube (e.g. "play Starboy on Spotify", "open Spotify and play Punjabi hits"):
   Use action tag: [ACTION: {"type": "play_music", "query": "Starboy", "platform": "spotify"}]
2. Media playback control (Play/Pause, Next song, Previous song):
   Use action tag: [ACTION: {"type": "media", "action": "play_pause"}] or [ACTION: {"type": "media", "action": "next"}]
3. Search Google / Web:
   Use action tag: [ACTION: {"type": "search", "query": "latest AI news"}]
4. Open apps / websites (e.g. Spotify, YouTube, Chrome, Notepad, Calculator, VS Code, WhatsApp, Discord):
   Use action tag: [ACTION: {"type": "open", "target": "spotify"}]
5. Minimize all windows / Show desktop:
   Use action tag: [ACTION: {"type": "minimize"}]
6. Restore / Unminimize windows:
   Use action tag: [ACTION: {"type": "restore"}]
7. Volume control:
   Use action tags: [ACTION: {"type": "volume_up"}], [ACTION: {"type": "volume_down"}], [ACTION: {"type": "mute"}]
8. Lock PC:
   Use action tag: [ACTION: {"type": "lock"}]

CRITICAL SPEECH RULES:
1. Plain spoken prose only. No markdown, no asterisks, no bullet points, no emoji.
2. Short, crisp, natural conversational style (1-2 sentences). You are speaking aloud to Tony Stark.

FLUENT BILINGUAL PERSONA (ENGLISH, HINDI & HINGLISH):
- You are seamlessly fluent in both English and natural Hindi/Hinglish.
- ALWAYS match the language of the user:
  * When the user speaks in Hindi or Hinglish (e.g. "tum kaun ho", "kya haal hai", "aaj mausam kaisa hai", "kuch sunao", "kya kar sakte ho"):
    Reply in fluent, natural, sophisticated conversational Hindi or Hinglish (e.g. "Main Jarvis hoon sir, aapka personal AI. Bataiye aaj kya madad karun?", "Bilkul sir, mausam saaf hai aur taapmaan 24 degree hai.").
  * Use a polite, composed, respectful tone (using "aap", "sir").
  * When the user speaks in English, reply in English.
  * When the user speaks in Hinglish, reply in articulate Hinglish.`

  return function handleGeminiConnection(socket) {
    console.log(`[jarvis:gemini] client connected (using Gemini API)`)

    const convSession = new ConversationSession(null, 'gemini-3.5-flash')

    // Notify HUD that Gemini & System Control are ready
    const serverList = [
      'gemini-3.5-flash (google)',
      'live-web-search (realtime)',
      'spotify-controller (media)',
      'memory-vault (long-term)',
      'system-control (windows)',
      'file-engine (local)',
      ...Object.keys(mcpServers),
    ]
    if (socket.readyState === socket.OPEN) {
      socket.send(JSON.stringify({ type: 'ready', servers: serverList }))
    }

    // Gemini contents history
    const contents = []
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

      // 1. Check for Memory commands ("mera naam X hai", "remember that X")
      const memReply = detectMemoryIntent(text)
      if (memReply) {
        sendTurn({ type: 'text', delta: memReply })
        sendTurn({ type: 'done', text: memReply, costUsd: 0 })
        convSession.addAssistantMessage(memReply)
        return
      }

      // 2. Direct intent detection for immediate execution
      const directIntent = detectSystemIntent(text)
      if (directIntent) {
        sendTurn({ type: 'tool', name: `system · ${directIntent.type || 'action'}` })
        if (directIntent.type === 'play_music') {
          playSpotifyMusic(directIntent.query || directIntent.song || '', directIntent.platform || 'spotify')
        } else if (directIntent.type === 'media') {
          controlSpotifyMedia(directIntent.action)
        } else {
          executeAction(directIntent)
        }
      }

      // 3. Live Real-Time Web Telemetry (Weather, News, Current Events)
      let liveWebContext = ''
      if (/\b(?:weather|temperature|mausam|news|headlines|today|stock|nifty|sensex|bitcoin|crypto|price|cricket|score|who is|what is)\b/i.test(text)) {
        try {
          sendTurn({ type: 'progress', name: 'live · web search', text: 'Fetching live telemetry...' })
          const webRes = await liveWebSearch(text)
          if (webRes) {
            liveWebContext = `\n[LIVE REAL-TIME DATA]:\n${webRes}\n`
            console.log(`[jarvis:gemini] live web data fetched for "${text}"`)
          }
        } catch (err) {
          console.warn('[jarvis:gemini] web search error:', err.message)
        }
      }

      const promptWithLiveData = liveWebContext
        ? `${text}\n${liveWebContext}\n(Answer concisely in 1-2 spoken sentences using this live data)`
        : text

      contents.push({ role: 'user', parts: [{ text: promptWithLiveData }] })

      // Keep context manageable (last 20 messages)
      if (contents.length > 20) {
        contents.splice(0, contents.length - 16)
      }

      const abortController = new AbortController()
      currentAbort = abortController

      let fullAssistantText = ''
      let executedFromModel = Boolean(directIntent)

      try {
        const apiKey = getGeminiKey()
        if (!apiKey) {
          throw new Error('No GEMINI_API_KEY found in .env.local')
        }

        // Dynamically inject user profile & long-term memory
        const memoryPrompt = getMemoryContextPrompt()
        const dynamicSystemPrompt = `${baseSystemPrompt}\n${memoryPrompt}`

        // Try candidate models in order if one experiences high demand
        let response = null
        let usedModel = CANDIDATE_MODELS[0]

        for (const model of CANDIDATE_MODELS) {
          usedModel = model
          const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:streamGenerateContent?alt=sse&key=${apiKey}`

          response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              system_instruction: {
                parts: [{ text: dynamicSystemPrompt }]
              },
              contents,
              generationConfig: {
                temperature: 0.7,
                maxOutputTokens: 512,
              }
            }),
            signal: abortController.signal,
          })

          if (response.ok) break
          if (response.status === 503) {
            console.warn(`[jarvis:gemini] ${model} 503 high demand, trying next model...`)
            continue
          }
          break
        }

        if (!response.ok) {
          const errText = await response.text()
          throw new Error(`Gemini error (${response.status}): ${errText}`)
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
            const cleanLine = line.trim()
            if (!cleanLine.startsWith('data:')) continue
            const jsonStr = cleanLine.replace(/^data:\s*/, '').trim()
            if (!jsonStr || jsonStr === '[DONE]') continue

            try {
              const chunk = JSON.parse(jsonStr)
              const parts = chunk.candidates?.[0]?.content?.parts ?? []
              for (const part of parts) {
                const token = part.text
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
                        if (actionObj.type === 'play_music') {
                          playSpotifyMusic(actionObj.query, actionObj.platform || 'spotify')
                        } else if (actionObj.type === 'media') {
                          controlSpotifyMedia(actionObj.action)
                        } else {
                          executeAction(actionObj)
                        }
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
          .replace(/[*_#`]/g, '')
          .trim()

        if (cleanAssistantText) {
          contents.push({ role: 'model', parts: [{ text: cleanAssistantText }] })
          convSession.addAssistantMessage(cleanAssistantText)
        }

        sendTurn({
          type: 'done',
          text: cleanAssistantText,
          costUsd: 0,
        })
      } catch (err) {
        if (err.name === 'AbortError') return
        console.error('[jarvis:gemini] chat error:', err)
        sendTurn({
          type: 'error',
          message: `Gemini error: ${err.message}`,
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
      console.log('[jarvis:gemini] client disconnected')
      if (currentAbort) {
        currentAbort.abort()
        currentAbort = null
      }
    })
  }
}
