/**
 * Long-Term Memory & User Profile Manager for J.A.R.V.I.S.
 * 
 * Persists user details, facts, preferences, and notes across sessions.
 * Injects memory context into the LLM system prompt.
 */

import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import process from 'node:process'

const MEMORY_DIR = join(process.cwd(), 'memory')
const PROFILE_FILE = join(MEMORY_DIR, 'user_profile.json')

const DEFAULT_PROFILE = {
  name: 'Sarthak',
  preferred_language: 'Hinglish & English',
  role: 'Creator / Operator',
  facts: [
    'User built J.A.R.V.I.S. holographic AI system',
    'Prefers crisp, witty, high-IQ conversational answers',
  ],
  preferences: {
    music: 'The Weeknd, Punjabi, Hip-hop',
    editor: 'Antigravity IDE / VS Code',
  },
  notes: [],
}

export function loadUserProfile() {
  try {
    if (existsSync(PROFILE_FILE)) {
      return JSON.parse(readFileSync(PROFILE_FILE, 'utf-8'))
    }
  } catch (err) {
    console.warn('[jarvis:memory] error reading profile:', err.message)
  }
  saveUserProfile(DEFAULT_PROFILE)
  return DEFAULT_PROFILE
}

export function saveUserProfile(profile) {
  try {
    writeFileSync(PROFILE_FILE, JSON.stringify(profile, null, 2), 'utf-8')
  } catch (err) {
    console.error('[jarvis:memory] error saving profile:', err.message)
  }
}

export function recordFact(fact) {
  if (!fact || typeof fact !== 'string') return
  const p = loadUserProfile()
  if (!p.facts.includes(fact.trim())) {
    p.facts.push(fact.trim())
    saveUserProfile(p)
    console.log(`[jarvis:memory] saved new fact: "${fact}"`)
  }
}

export function setUserName(name) {
  if (!name) return
  const p = loadUserProfile()
  p.name = name.trim()
  saveUserProfile(p)
  console.log(`[jarvis:memory] updated user name: "${name}"`)
}

export function addNote(note) {
  if (!note) return
  const p = loadUserProfile()
  p.notes.push({ text: note.trim(), date: new Date().toISOString() })
  saveUserProfile(p)
}

/**
 * Detects if user utterance contains a memory / remember command
 */
export function detectMemoryIntent(text) {
  if (!text || typeof text !== 'string') return null
  const t = text.trim()

  // Name detection: "my name is X", "mera naam X hai", "call me X"
  const nameEn = t.match(/^(?:my\s+name\s+is|call\s+me)\s+([a-zA-Z]+)/i)
  if (nameEn && nameEn[1]) {
    setUserName(nameEn[1])
    return `Noted, sir. I shall address you as ${nameEn[1]}.`
  }

  const nameHi = t.match(/^(?:mera\s+naam)\s+([a-zA-Z]+)(?:\s+hai)?/i)
  if (nameHi && nameHi[1]) {
    setUserName(nameHi[1])
    return `Bilkul sir, ab se aapko ${nameHi[1]} kehkar bulaunga.`
  }

  // Fact storage: "remember that X", "yaad rakhna ki X", "note that X"
  const factEn = t.match(/^(?:remember\s+(?:that)?|note\s+(?:that)?)\s+(.+)$/i)
  if (factEn && factEn[1]) {
    recordFact(factEn[1])
    return 'Committed to long-term memory, sir.'
  }

  const factHi = t.match(/^(?:yaad\s+rakhna\s+(?:ki)?)\s+(.+)$/i)
  if (factHi && factHi[1]) {
    recordFact(factHi[1])
    return 'Memory databanks me store kar liya hai, sir.'
  }

  return null
}

/**
 * Generates the memory context prompt snippet to inject into LLM system prompt
 */
export function getMemoryContextPrompt() {
  const p = loadUserProfile()
  let prompt = `\nUSER IDENTITY & LONG-TERM MEMORY:\n`
  prompt += `- User's Name: ${p.name || 'Sir'}\n`
  prompt += `- Preferred Language: ${p.preferred_language}\n`
  if (p.facts && p.facts.length > 0) {
    prompt += `- Stored Facts:\n`
    for (const f of p.facts) {
      prompt += `  * ${f}\n`
    }
  }
  if (p.preferences) {
    prompt += `- Preferences: Music: ${p.preferences.music}, Editor: ${p.preferences.editor}\n`
  }
  prompt += `Always recognize the user by their name (${p.name || 'sir'}).\n`
  return prompt
}
