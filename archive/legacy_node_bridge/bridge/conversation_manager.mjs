import { existsSync, mkdirSync, readFileSync, writeFileSync, unlinkSync } from 'node:fs'
import { join } from 'node:path'
import process from 'node:process'

const CONVERSATIONS_DIR = join(process.cwd(), 'conversations')

// Ensure conversations directory exists
if (!existsSync(CONVERSATIONS_DIR)) {
  mkdirSync(CONVERSATIONS_DIR, { recursive: true })
}

const INDEX_FILE = join(CONVERSATIONS_DIR, 'index.json')

function getTimestamp() {
  const now = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}_${pad(now.getHours())}-${pad(now.getMinutes())}-${pad(now.getSeconds())}`
}

function loadIndex() {
  try {
    if (existsSync(INDEX_FILE)) {
      return JSON.parse(readFileSync(INDEX_FILE, 'utf-8'))
    }
  } catch (err) {
    console.warn('[jarvis:conversations] error reading index.json:', err.message)
  }
  return []
}

function saveIndex(index) {
  try {
    writeFileSync(INDEX_FILE, JSON.stringify(index, null, 2), 'utf-8')
  } catch (err) {
    console.error('[jarvis:conversations] error writing index.json:', err.message)
  }
}

function sanitizeTitle(title) {
  if (!title) return 'Conversation'
  // Remove Windows-restricted filename chars: \ / : * ? " < > |
  let clean = title.replace(/[\\/:*?"<>|]/g, '').replace(/\s+/g, ' ').trim()
  if (clean.length > 60) clean = clean.slice(0, 57) + '...'
  return clean || 'Conversation'
}

export class ConversationSession {
  constructor(sessionId = null, provider = 'unknown') {
    this.id = sessionId || `session_${getTimestamp()}`
    this.provider = provider
    this.title = 'New Conversation'
    this.createdAt = new Date().toISOString()
    this.updatedAt = this.createdAt
    this.turns = []

    this.filename = sanitizeTitle(this.title)
    this.jsonPath = join(CONVERSATIONS_DIR, `${this.filename}.json`)
    this.mdPath = join(CONVERSATIONS_DIR, `${this.filename}.md`)
  }

  addUserMessage(text) {
    if (!text || typeof text !== 'string') return
    const trimmed = text.trim()
    if (!trimmed) return

    // Auto-derive title from first user query
    if (this.turns.length === 0 || this.title === 'New Conversation') {
      const oldJsonPath = this.jsonPath
      const oldMdPath = this.mdPath

      this.title = trimmed.length > 50 ? trimmed.slice(0, 47) + '...' : trimmed
      this.filename = sanitizeTitle(this.title)
      this.jsonPath = join(CONVERSATIONS_DIR, `${this.filename}.json`)
      this.mdPath = join(CONVERSATIONS_DIR, `${this.filename}.md`)

      // Clean up previous placeholder file if named differently
      if (oldJsonPath !== this.jsonPath) {
        try {
          if (existsSync(oldJsonPath)) unlinkSync(oldJsonPath)
          if (existsSync(oldMdPath)) unlinkSync(oldMdPath)
        } catch {
          // ignore
        }
      }
    }

    const now = new Date().toISOString()
    this.updatedAt = now
    this.turns.push({
      role: 'user',
      text: trimmed,
      timestamp: now,
    })

    this._save()
    this._updateIndex()
  }

  addAssistantMessage(text, meta = {}) {
    if (!text || typeof text !== 'string') return
    const trimmed = text.trim()
    if (!trimmed) return

    const now = new Date().toISOString()
    this.updatedAt = now
    this.turns.push({
      role: 'assistant',
      text: trimmed,
      timestamp: now,
      ...meta,
    })

    this._save()
    this._updateIndex()
  }

  _save() {
    try {
      const data = {
        id: this.id,
        title: this.title,
        provider: this.provider,
        created_at: this.createdAt,
        updated_at: this.updatedAt,
        turn_count: this.turns.length,
        turns: this.turns,
      }
      writeFileSync(this.jsonPath, JSON.stringify(data, null, 2), 'utf-8')

      // Write human readable Markdown transcript
      let md = `# Session: ${this.title}\n\n`
      md += `- **Session ID:** \`${this.id}\`\n`
      md += `- **Provider:** ${this.provider}\n`
      md += `- **Started:** ${this.createdAt}\n`
      md += `- **Last Updated:** ${this.updatedAt}\n\n`
      md += `---\n\n`

      for (const t of this.turns) {
        const time = t.timestamp ? t.timestamp.split('T')[1].slice(0, 8) : ''
        if (t.role === 'user') {
          md += `### 👤 User (${time})\n${t.text}\n\n`
        } else {
          md += `### 🤖 Jarvis (${time})\n${t.text}\n\n`
          if (t.tools && t.tools.length) {
            md += `> *Tools executed:* ${t.tools.join(', ')}\n\n`
          }
        }
      }

      writeFileSync(this.mdPath, md, 'utf-8')
    } catch (err) {
      console.error(`[jarvis:conversations] error saving session ${this.id}:`, err.message)
    }
  }

  _updateIndex() {
    try {
      const index = loadIndex()
      const existingIdx = index.findIndex((s) => s.id === this.id)
      const entry = {
        id: this.id,
        title: this.title,
        provider: this.provider,
        created_at: this.createdAt,
        updated_at: this.updatedAt,
        turn_count: this.turns.length,
        json_file: `${this.filename}.json`,
        md_file: `${this.filename}.md`,
      }

      if (existingIdx >= 0) {
        index[existingIdx] = entry
      } else {
        index.unshift(entry)
      }

      // Sort newest updated first
      index.sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at))
      saveIndex(index)
    } catch (err) {
      console.error('[jarvis:conversations] error updating index:', err.message)
    }
  }
}

export function listConversations() {
  return loadIndex()
}

export function getConversation(nameOrId) {
  try {
    const raw = (nameOrId || '').replace(/\.json$/i, '')
    // Try direct filename
    const directFile = join(CONVERSATIONS_DIR, `${raw}.json`)
    if (existsSync(directFile)) {
      return JSON.parse(readFileSync(directFile, 'utf-8'))
    }
    // Try matching by id in index
    const index = loadIndex()
    const found = index.find((e) => e.id === nameOrId || e.title === nameOrId)
    if (found && found.json_file) {
      const matchFile = join(CONVERSATIONS_DIR, found.json_file)
      if (existsSync(matchFile)) {
        return JSON.parse(readFileSync(matchFile, 'utf-8'))
      }
    }
  } catch (err) {
    console.error(`[jarvis:conversations] error loading session ${nameOrId}:`, err.message)
  }
  return null
}
