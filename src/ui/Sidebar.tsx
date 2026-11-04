import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useStore, type Turn } from '../store'

interface ConversationSummary {
  id: string
  preview: string
  created_at: number
  updated_at: number
  turn_count: number
  origin: string
  metadata?: Record<string, any>
}

export function Sidebar() {
  const [isOpen, setIsOpen] = useState(false)
  const [filter, setFilter] = useState<'all' | 'voice' | 'telegram'>('all')
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const setTurns = useStore((s) => s.setTurns)
  const clearTurns = useStore((s) => s.clearTurns)

  const fetchConversations = useCallback(async () => {
    try {
      setLoading(true)
      const res = await fetch('http://127.0.0.1:8000/api/conversations?limit=40')
      if (res.ok) {
        const data = await res.json()
        setConversations(data.conversations || [])
      }
    } catch (e) {
      console.warn('[Sidebar] Error fetching conversations:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (isOpen) {
      fetchConversations()
    }
  }, [isOpen, fetchConversations])

  // Keyboard shortcut Ctrl+H to toggle sidebar
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'h') {
        e.preventDefault()
        setIsOpen((prev) => !prev)
      } else if (e.key === 'Escape' && isOpen) {
        setIsOpen(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen])

  const handleSelectSession = async (session: ConversationSummary) => {
    try {
      setSelectedId(session.id)
      const res = await fetch(`http://127.0.0.1:8000/api/conversations/${session.id}`)
      if (res.ok) {
        const data = await res.json()
        const turns: Turn[] = (data.turns || []).map((t: any) => ({
          id: t.id,
          role: t.role === 'assistant' ? 'jarvis' : 'user',
          text: t.content,
          tools: t.tool_action ? [t.tool_action.type || 'action'] : undefined,
          source: t.content.includes('[Telegram') || session.origin === 'telegram' ? 'telegram' : 'voice',
          timestamp: t.timestamp * 1000,
        }))
        setTurns(turns)
      }
    } catch (e) {
      console.error('[Sidebar] Failed to load session turns:', e)
    }
  }

  const handleNewSession = async () => {
    try {
      await fetch('http://127.0.0.1:8000/api/session/new', { method: 'POST' })
      clearTurns()
      setSelectedId(null)
      fetchConversations()
    } catch (e) {
      console.error('[Sidebar] Failed to start new session:', e)
    }
  }

  // Filter conversations
  const filteredConversations = conversations.filter((c) => {
    if (filter === 'voice') return c.origin !== 'telegram'
    if (filter === 'telegram') return c.origin === 'telegram' || c.preview.includes('[Telegram')
    return true
  })

  // Date grouping
  const now = Date.now() / 1000
  const isToday = (ts: number) => now - ts < 86400
  const isYesterday = (ts: number) => now - ts >= 86400 && now - ts < 172800

  const todaySessions = filteredConversations.filter((c) => isToday(c.updated_at))
  const yesterdaySessions = filteredConversations.filter((c) => isYesterday(c.updated_at))
  const olderSessions = filteredConversations.filter((c) => !isToday(c.updated_at) && !isYesterday(c.updated_at))

  return (
    <>
      {/* Sleek Floating Trigger Button in Top Left */}
      <div className="sidebar-trigger-container">
        <button
          className={`sidebar-toggle-btn ${isOpen ? 'active' : ''}`}
          onClick={() => setIsOpen(!isOpen)}
          title="Toggle Chat Sessions & Telegram Audit Log (Ctrl+H)"
        >
          <span className="toggle-icon">☰</span>
          <span className="toggle-label">HISTORY & AUDIT</span>
          <span className="live-dot" />
        </button>
      </div>

      {/* Slide-out Backdrop Overlay */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            className="sidebar-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setIsOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* Slide-out Sidebar Drawer */}
      <AnimatePresence>
        {isOpen && (
          <motion.aside
            className="chat-sidebar"
            initial={{ x: '-100%', opacity: 0.8 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: '-100%', opacity: 0.8 }}
            transition={{ type: 'spring', damping: 28, stiffness: 260 }}
          >
            {/* Header */}
            <div className="sidebar-header">
              <div className="sidebar-title-group">
                <span className="sidebar-title">MISSION ARCHIVE</span>
                <span className="sidebar-badge">AUDIT TRAIL</span>
              </div>
              <button className="sidebar-close-btn" onClick={() => setIsOpen(false)}>
                ✕
              </button>
            </div>

            {/* New Session Action */}
            <button className="new-chat-btn" onClick={handleNewSession}>
              <span className="plus-icon">+</span>
              <span>START NEW SESSION</span>
            </button>

            {/* Filter Pills */}
            <div className="filter-pill-row">
              <button
                className={`filter-pill ${filter === 'all' ? 'active' : ''}`}
                onClick={() => setFilter('all')}
              >
                ALL
              </button>
              <button
                className={`filter-pill ${filter === 'voice' ? 'active' : ''}`}
                onClick={() => setFilter('voice')}
              >
                🎙️ VOICE
              </button>
              <button
                className={`filter-pill ${filter === 'telegram' ? 'active' : ''}`}
                onClick={() => setFilter('telegram')}
              >
                📱 TELEGRAM
              </button>
            </div>

            {/* Sessions Scrollable Container */}
            <div className="sidebar-scroll-area">
              {loading && conversations.length === 0 && (
                <div className="sidebar-loading">Scanning memory database...</div>
              )}

              {filteredConversations.length === 0 && !loading && (
                <div className="sidebar-empty">No logged sessions in this category.</div>
              )}

              {/* Group: Today */}
              {todaySessions.length > 0 && (
                <div className="session-group">
                  <div className="group-heading">TODAY</div>
                  {todaySessions.map((session) => (
                    <SessionCard
                      key={session.id}
                      session={session}
                      isSelected={selectedId === session.id}
                      onSelect={() => handleSelectSession(session)}
                    />
                  ))}
                </div>
              )}

              {/* Group: Yesterday */}
              {yesterdaySessions.length > 0 && (
                <div className="session-group">
                  <div className="group-heading">YESTERDAY</div>
                  {yesterdaySessions.map((session) => (
                    <SessionCard
                      key={session.id}
                      session={session}
                      isSelected={selectedId === session.id}
                      onSelect={() => handleSelectSession(session)}
                    />
                  ))}
                </div>
              )}

              {/* Group: Older */}
              {olderSessions.length > 0 && (
                <div className="session-group">
                  <div className="group-heading">OLDER SESSIONS</div>
                  {olderSessions.map((session) => (
                    <SessionCard
                      key={session.id}
                      session={session}
                      isSelected={selectedId === session.id}
                      onSelect={() => handleSelectSession(session)}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Telegram Security Sentinel Monitor (Bottom Audit Card) */}
            <div className="telegram-audit-sentinel">
              <div className="sentinel-header">
                <span className="sentinel-dot" />
                <span className="sentinel-title">TELEGRAM SECURITY SENTINEL</span>
              </div>
              <div className="sentinel-body">
                <div className="sentinel-row">
                  <span className="label">BOT GATEWAY:</span>
                  <span className="val cyan">@Phoenix_sarthak_bot</span>
                </div>
                <div className="sentinel-row">
                  <span className="label">AUDIT STATUS:</span>
                  <span className="val green">GUARD ACTIVE</span>
                </div>
                <div className="sentinel-notice">
                  All remote commands are logged with sender identity & timestamps.
                </div>
              </div>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  )
}

function SessionCard({
  session,
  isSelected,
  onSelect,
}: {
  session: ConversationSummary
  isSelected: boolean
  onSelect: () => void
}) {
  const isTelegram = session.origin === 'telegram' || session.preview.includes('[Telegram')
  const formattedTime = new Date(session.updated_at * 1000).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <div
      className={`session-card ${isSelected ? 'selected' : ''} ${isTelegram ? 'telegram-origin' : ''}`}
      onClick={onSelect}
    >
      <div className="session-top">
        <span className={`origin-badge ${isTelegram ? 'badge-telegram' : 'badge-voice'}`}>
          {isTelegram ? '📱 TELEGRAM' : '🎙️ VOICE'}
        </span>
        <span className="session-time">{formattedTime}</span>
      </div>
      <div className="session-preview">{session.preview || 'Untitled Interaction'}</div>
      <div className="session-footer">
        <span className="turn-count">{session.turn_count} turns</span>
        <span className="inspect-hint">Click to inspect</span>
      </div>
    </div>
  )
}
