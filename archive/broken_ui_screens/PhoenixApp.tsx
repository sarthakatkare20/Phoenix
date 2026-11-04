import { useState, useEffect } from 'react'
import { useStore, type Turn } from '../store'
import './phoenix-mission-control.css'

import { Screen01Launch } from './screens/Screen01Launch'
import { Screen02Home } from './screens/Screen02Home'
import { Screen03Chats } from './screens/Screen03Chats'
import { Screen04Voice } from './screens/Screen04Voice'
import { Screen05Telegram } from './screens/Screen05Telegram'
import { Screen06Activity } from './screens/Screen06Activity'
import { Screen07Security } from './screens/Screen07Security'
import { Screen08Settings } from './screens/Screen08Settings'

interface PhoenixAppProps {
  onSendMessage: (text: string) => void
  onToggleVoice: () => void
  isVoiceListening: boolean
  onPowerOn: () => void
}

interface ConversationItem {
  id: string
  preview: string
  updated_at: number
  origin: string
  turn_count: number
}

// ---------------------------------------------------------------------------
// Vector Icons
// ---------------------------------------------------------------------------

function FlameIcon({ size = 26, glow = true }: { size?: number; glow?: boolean }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      style={glow ? { filter: 'drop-shadow(0 0 8px rgba(255, 138, 36, 0.5))' } : {}}
    >
      <defs>
        <linearGradient id="phxFlameGradMain" x1="12" y1="2" x2="12" y2="22" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#ffb300" />
          <stop offset="45%" stopColor="#ff6d00" />
          <stop offset="100%" stopColor="#ff3d00" />
        </linearGradient>
      </defs>
      <path
        d="M12 2C10.5 4.5 10 6 10 7.5C10 8.5 10.5 9.5 11.5 10C9 9.5 7.5 8 7 6.5C5.5 8.5 5 11 5 13C5 17 8 21 12 21C16 21 19 17 19 13C19 9.5 17.5 6.5 15 4C15 6 14.5 7 13.5 7.5C13.5 6 13 4 12 2Z"
        fill="url(#phxFlameGradMain)"
      />
      <path
        d="M12 11C11 12 10.5 13 10.5 14C10.5 15.5 11.2 16.5 12 17C12.8 16.5 13.5 15.5 13.5 14C13.5 13 13 12 12 11Z"
        fill="#ffe082"
      />
    </svg>
  )
}

function ChatsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  )
}

function ActivityIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 14 14" />
    </svg>
  )
}

function RemoteIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  )
}

function SecurityIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  )
}

function SettingsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  )
}

function MicIcon({ active = false }: { active?: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={active ? '#00e5d4' : 'currentColor'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  )
}

function PaperclipIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
    </svg>
  )
}

function SendPlaneIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" fill="#ffffff" />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// PhoenixApp Main Mission Control Container
// ---------------------------------------------------------------------------

export function PhoenixApp({
  onSendMessage,
  onToggleVoice,
  isVoiceListening,
  onPowerOn,
}: PhoenixAppProps) {
  const [activeTab, setActiveTab] = useState<'chats' | 'activity' | 'remote' | 'security' | 'settings'>('chats')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [inputText, setInputText] = useState('')
  const [recentItems, setRecentItems] = useState<ConversationItem[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [activeSessionTitle, setActiveSessionTitle] = useState('Spotify music')
  const [activeSessionOrigin, setActiveSessionOrigin] = useState('voice')
  const [showVoiceOverlay, setShowVoiceOverlay] = useState(false)
  const [showLaunchChecklist, setShowLaunchChecklist] = useState(false)

  const turns = useStore((s) => s.turns)
  const caption = useStore((s) => s.caption)
  const phase = useStore((s) => s.phase)
  const activeTool = useStore((s) => s.activeTool)
  const level = useStore((s) => s.level)
  const setTurns = useStore((s) => s.setTurns)
  const clearTurns = useStore((s) => s.clearTurns)

  // Fetch real conversation sessions from SQLite backend
  const refreshConversations = () => {
    fetch('http://127.0.0.1:8000/api/conversations?limit=25')
      .then((r) => r.json())
      .then((data) => {
        if (data.conversations && data.conversations.length > 0) {
          setRecentItems(data.conversations)
          if (!activeSessionId && data.conversations[0]) {
            setActiveSessionId(data.conversations[0].id)
            setActiveSessionTitle(data.conversations[0].preview || 'Spotify music')
            setActiveSessionOrigin(data.conversations[0].origin || 'voice')
          }
        } else {
          setRecentItems([
            { id: 'sess-1', preview: 'Spotify music', updated_at: Date.now() / 1000 - 600, origin: 'voice', turn_count: 4 },
            { id: 'sess-2', preview: 'Status check', updated_at: Date.now() / 1000 - 86400, origin: 'telegram', turn_count: 2 },
            { id: 'sess-3', preview: 'Refactor UI', updated_at: Date.now() / 1000 - 259200, origin: 'ide', turn_count: 6 },
          ])
        }
      })
      .catch(() => {})
  }

  useEffect(() => {
    refreshConversations()
  }, [])

  const ensurePower = () => {
    if (phase === 'offline') {
      onPowerOn()
    }
  }

  const handleSend = () => {
    if (!inputText.trim()) return
    ensurePower()
    onSendMessage(inputText.trim())
    setInputText('')
    if (activeTab !== 'chats') {
      setActiveTab('chats')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleVoiceToggle = () => {
    ensurePower()
    onToggleVoice()
    setShowVoiceOverlay(true)
  }

  const handleStartNewSession = async () => {
    try {
      const res = await fetch('http://127.0.0.1:8000/api/session/new', { method: 'POST' })
      const d = await res.json()
      clearTurns()
      if (d.session) {
        setActiveSessionId(d.session.id)
      } else {
        setActiveSessionId(null)
      }
      setActiveSessionTitle('New Interaction')
      setActiveSessionOrigin('voice')
      refreshConversations()
      setActiveTab('chats')
    } catch {
      clearTurns()
    }
  }

  const loadPastSession = async (sessionItem: ConversationItem) => {
    try {
      setActiveSessionId(sessionItem.id)
      setActiveSessionTitle(sessionItem.preview || 'Conversation')
      setActiveSessionOrigin(sessionItem.origin || 'voice')
      const res = await fetch(`http://127.0.0.1:8000/api/conversations/${sessionItem.id}`)
      if (res.ok) {
        const d = await res.json()
        const loaded: Turn[] = (d.turns || []).map((t: any) => ({
          id: t.id,
          role: t.role === 'assistant' ? 'jarvis' : 'user',
          text: t.content,
          tools: t.tool_action ? [t.tool_action.type || 'action'] : undefined,
          source: t.content.includes('[Telegram') ? 'telegram' : 'voice',
          timestamp: t.timestamp * 1000,
        }))
        setTurns(loaded)
        setActiveTab('chats')
      }
    } catch (e) {
      console.warn('Failed to load past session', e)
    }
  }

  const handleRenameSession = async (id: string, newTitle: string) => {
    try {
      await fetch(`http://127.0.0.1:8000/api/conversations/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle }),
      })
      setActiveSessionTitle(newTitle)
      refreshConversations()
    } catch (e) {
      console.warn('Failed to rename session', e)
    }
  }

  const handleDeleteSession = async (id: string) => {
    try {
      await fetch(`http://127.0.0.1:8000/api/conversations/${id}`, {
        method: 'DELETE',
      })
      clearTurns()
      setActiveSessionId(null)
      refreshConversations()
    } catch (e) {
      console.warn('Failed to delete session', e)
    }
  }

  const handleExecuteToolAction = async (actionType: string, target: string) => {
    ensurePower()
    try {
      await fetch('http://127.0.0.1:8000/api/computer/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: actionType, target }),
      })
    } catch (e) {
      console.warn('Tool action failed:', e)
    }
  }

  const handleLaunchIDE = async () => {
    ensurePower()
    try {
      await fetch('http://127.0.0.1:8000/api/visual/antigravity', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: 'Focus Antigravity IDE' }),
      })
      onSendMessage('Focus and bring up Antigravity IDE workspace')
    } catch {
      onSendMessage('Open Antigravity IDE')
    }
    setActiveTab('chats')
  }

  const handleWindowAction = async (action: 'minimize' | 'restore' | 'lock') => {
    try {
      await fetch('http://127.0.0.1:8000/api/computer/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: 'system_control',
          target: action,
        }),
      })
    } catch (e) {
      console.warn('Window control error:', e)
    }
  }

  const formatRecentTime = (ts: number) => {
    const diff = Date.now() / 1000 - ts
    if (diff < 86400) {
      return new Date(ts * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    } else if (diff < 172800) {
      return 'Yesterday'
    } else {
      return new Date(ts * 1000).toLocaleDateString([], { month: 'short', day: 'numeric' })
    }
  }

  return (
    <div className="phoenix-window-container">
      {/* ----------------------------------------------------------------- */}
      {/* SCREEN 01: LAUNCH & INITIALIZATION MODAL                          */}
      {/* ----------------------------------------------------------------- */}
      <Screen01Launch
        isOpen={showLaunchChecklist}
        onComplete={() => setShowLaunchChecklist(false)}
        onClose={() => setShowLaunchChecklist(false)}
      />

      {/* ----------------------------------------------------------------- */}
      {/* SCREEN 04: DEDICATED VOICE INTERACTION OVERLAY                    */}
      {/* ----------------------------------------------------------------- */}
      {showVoiceOverlay && (
        <Screen04Voice
          phase={phase}
          level={level}
          caption={caption}
          onToggleVoice={onToggleVoice}
          onClose={() => setShowVoiceOverlay(false)}
        />
      )}

      {/* ----------------------------------------------------------------- */}
      {/* LEFT SIDEBAR                                                      */}
      {/* ----------------------------------------------------------------- */}
      <aside className={`phoenix-sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
        {/* Brand Row */}
        <div className="sidebar-brand-row">
          <div className="brand-badge-group">
            <FlameIcon size={26} />
            {!sidebarCollapsed && (
              <div className="brand-text-column">
                <span className="brand-title">Phoenix</span>
                <span className="brand-subtitle">AI Assistant</span>
              </div>
            )}
          </div>
          <button
            className="collapse-toggle-btn"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            title={sidebarCollapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
          >
            {sidebarCollapsed ? '»' : '«'}
          </button>
        </div>

        {/* Primary Navigation Tabs */}
        <nav className="sidebar-nav">
          <button
            className={`nav-item ${activeTab === 'chats' ? 'active' : ''}`}
            onClick={() => setActiveTab('chats')}
          >
            <ChatsIcon />
            {!sidebarCollapsed && <span>Chats</span>}
          </button>

          <button
            className={`nav-item ${activeTab === 'activity' ? 'active' : ''}`}
            onClick={() => setActiveTab('activity')}
          >
            <ActivityIcon />
            {!sidebarCollapsed && <span>Activity</span>}
          </button>

          <button
            className={`nav-item ${activeTab === 'remote' ? 'active' : ''}`}
            onClick={() => setActiveTab('remote')}
          >
            <RemoteIcon />
            {!sidebarCollapsed && <span>Remote Activity</span>}
          </button>

          <button
            className={`nav-item ${activeTab === 'security' ? 'active' : ''}`}
            onClick={() => setActiveTab('security')}
          >
            <SecurityIcon />
            {!sidebarCollapsed && <span>Security Center</span>}
          </button>

          <button
            className={`nav-item ${activeTab === 'settings' ? 'active' : ''}`}
            onClick={() => setActiveTab('settings')}
          >
            <SettingsIcon />
            {!sidebarCollapsed && <span>Settings</span>}
          </button>
        </nav>

        {/* Recent Conversations */}
        {!sidebarCollapsed && (
          <div className="sidebar-recent-section">
            <div className="recent-header-row">
              <span className="recent-header">Recent</span>
              <button
                className="new-chat-tiny-btn"
                onClick={handleStartNewSession}
                title="Start New Session"
              >
                + New
              </button>
            </div>
            <div className="recent-list">
              {recentItems.map((item) => (
                <div
                  key={item.id}
                  className={`recent-item ${activeSessionId === item.id ? 'active-recent' : ''}`}
                  onClick={() => loadPastSession(item)}
                >
                  <div className="recent-left">
                    <span className="recent-icon">
                      {item.origin === 'telegram' ? '📱' : item.origin === 'ide' ? '💻' : '💬'}
                    </span>
                    <span className="recent-title">{item.preview || 'Untitled Interaction'}</span>
                  </div>
                  <span className="recent-time">{formatRecentTime(item.updated_at)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Bottom User Profile */}
        <div className="sidebar-user-profile">
          <div className="profile-avatar-wrapper">
            <div className="profile-avatar">S</div>
            <span className="profile-status-dot" />
          </div>
          {!sidebarCollapsed && (
            <div className="profile-text-col">
              <span className="profile-name">Sarthak</span>
              <span className="profile-role">Mission Controller</span>
            </div>
          )}
        </div>
      </aside>

      {/* ----------------------------------------------------------------- */}
      {/* MAIN CONTENT STAGE (3D Arc Reactor Visible in Center Behind UI)   */}
      {/* ----------------------------------------------------------------- */}
      <main className="phoenix-main-stage">
        {/* Top Window Bar */}
        <header className="main-top-bar">
          <div className="top-bar-left">
            {sidebarCollapsed && (
              <button className="expand-sidebar-pill" onClick={() => setSidebarCollapsed(false)}>
                »
              </button>
            )}
            {/* Live Audio Level Meter */}
            <div className="signal-audio-meter">
              <span className="meter-label">SIGNAL</span>
              <div className="meter-bar-track">
                <div className="meter-bar-fill" style={{ width: `${Math.round(level * 100)}%` }} />
              </div>
            </div>
          </div>

          <div className="top-bar-right">
            {/* Clickable System Readiness Checklist Pill */}
            <button
              className="checklist-launch-pill"
              onClick={() => setShowLaunchChecklist(true)}
              title="View Startup Telemetry Checklist"
            >
              <span>System Ready ✓</span>
            </button>

            <div className="status-online-pill">
              <span className="pulse-green-dot" />
              <span>{phase === 'offline' ? 'Standby (Click to Init)' : 'Online'}</span>
            </div>

            <div className="window-controls">
              <button className="win-btn" onClick={() => handleWindowAction('minimize')} title="Minimize Windows">−</button>
              <button className="win-btn" onClick={() => handleWindowAction('restore')} title="Restore Windows">□</button>
              <button className="win-btn win-close" onClick={() => handleWindowAction('lock')} title="Lock PC">✕</button>
            </div>
          </div>
        </header>

        {/* Dynamic View Body */}
        <div className="main-stage-body">
          {/* TAB: CHATS */}
          {activeTab === 'chats' && (
            <>
              {/* When no turns in active session: Screen 02 Home / Mission Control */}
              {turns.length === 0 ? (
                <Screen02Home
                  onVoiceClick={handleVoiceToggle}
                  onTelegramClick={() => setActiveTab('remote')}
                  onIDEClick={handleLaunchIDE}
                  onViewActivityClick={() => setActiveTab('activity')}
                  isVoiceListening={isVoiceListening}
                  phase={phase}
                  onPowerOn={onPowerOn}
                />
              ) : (
                /* When turns exist: Screen 03 ChatGPT-style Chat Stream */
                <Screen03Chats
                  turns={turns}
                  caption={caption}
                  activeTool={activeTool}
                  sessionId={activeSessionId}
                  sessionTitle={activeSessionTitle}
                  sessionOrigin={activeSessionOrigin}
                  onRenameSession={handleRenameSession}
                  onDeleteSession={handleDeleteSession}
                  onStartNewSession={handleStartNewSession}
                  onExecuteToolAction={handleExecuteToolAction}
                />
              )}
            </>
          )}

          {/* TAB: ACTIVITY (Screen 06) */}
          {activeTab === 'activity' && <Screen06Activity />}

          {/* TAB: REMOTE ACTIVITY (Screen 05 Telegram Remote) */}
          {activeTab === 'remote' && (
            <Screen05Telegram onRefreshActivity={refreshConversations} />
          )}

          {/* TAB: SECURITY CENTER (Screen 07) */}
          {activeTab === 'security' && <Screen07Security />}

          {/* TAB: SETTINGS & CUSTOMIZATION (Screen 08) */}
          {activeTab === 'settings' && <Screen08Settings />}
        </div>

        {/* ----------------------------------------------------------------- */}
        {/* BOTTOM FLOATING COMMAND INPUT BAR (Ask Phoenix anything...)       */}
        {/* ----------------------------------------------------------------- */}
        <div className="chat-input-bar-container">
          <div className={`chat-input-pill-wrapper ${isVoiceListening ? 'voice-active-border' : ''}`}>
            {/* Mic Button */}
            <button
              className={`pill-mic-btn ${isVoiceListening ? 'listening' : ''}`}
              onClick={handleVoiceToggle}
              title={isVoiceListening ? 'Mic Active - Click to Stop' : 'Click to Speak'}
            >
              <MicIcon active={isVoiceListening} />
            </button>

            {/* Text Input */}
            <input
              type="text"
              className="pill-text-input"
              placeholder="Ask Phoenix anything..."
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
            />

            {/* Paperclip Button */}
            <button className="pill-clip-btn" title="Attach context file">
              <PaperclipIcon />
            </button>

            {/* Send Button */}
            <button className="pill-send-btn" onClick={handleSend} title="Send prompt">
              <SendPlaneIcon />
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}
