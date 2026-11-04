import { useState, useRef, useEffect } from 'react'
import { motion } from 'framer-motion'
import { type Turn } from '../../store'

interface Screen03ChatsProps {
  turns: Turn[]
  caption: string
  activeTool: string | null
  sessionId: string | null
  sessionTitle?: string
  sessionOrigin?: string
  onRenameSession: (id: string, newTitle: string) => void
  onDeleteSession: (id: string) => void
  onStartNewSession: () => void
  onExecuteToolAction: (actionType: string, target: string) => void
}

export function Screen03Chats({
  turns,
  caption,
  activeTool,
  sessionId,
  sessionTitle = 'Spotify music',
  sessionOrigin = 'voice',
  onRenameSession,
  onDeleteSession,
  onStartNewSession,
  onExecuteToolAction,
}: Screen03ChatsProps) {
  const [isRenaming, setIsRenaming] = useState(false)
  const [renameInput, setRenameInput] = useState(sessionTitle)
  const [copiedCodeId, setCopiedCodeId] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const chatScrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setRenameInput(sessionTitle)
  }, [sessionTitle])

  useEffect(() => {
    if (chatScrollRef.current) {
      chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight
    }
  }, [turns, caption])

  const handleSaveRename = () => {
    if (sessionId && renameInput.trim()) {
      onRenameSession(sessionId, renameInput.trim())
    }
    setIsRenaming(false)
  }

  const handleCopyCode = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedCodeId(id)
    setTimeout(() => setCopiedCodeId(null), 2000)
  }

  return (
    <div className="screen-chats-container">
      {/* ------------------------------------------------------------- */}
      {/* CONVERSATION HEADER                                           */}
      {/* ------------------------------------------------------------- */}
      <header className="chat-header-bar">
        <div className="chat-header-left">
          {isRenaming ? (
            <div className="rename-inline-box">
              <input
                type="text"
                className="rename-input-field"
                value={renameInput}
                onChange={(e) => setRenameInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSaveRename()}
                autoFocus
              />
              <button className="rename-action-btn check" onClick={handleSaveRename}>✓</button>
              <button className="rename-action-btn cancel" onClick={() => setIsRenaming(false)}>✕</button>
            </div>
          ) : (
            <div className="title-origin-group">
              <span className="session-title-text">{sessionTitle}</span>
              <button
                className="edit-title-btn"
                onClick={() => setIsRenaming(true)}
                title="Rename conversation"
              >
                ✏️
              </button>
              <span className="session-origin-badge">
                {sessionOrigin === 'telegram' ? '📱 Telegram' : sessionOrigin === 'ide' ? '💻 IDE' : '🎙️ Voice'}
              </span>
            </div>
          )}
        </div>

        <div className="chat-header-right">
          <button className="new-session-pill-btn" onClick={onStartNewSession}>
            + New Session
          </button>

          {sessionId && (
            <>
              {confirmDelete ? (
                <div className="confirm-delete-group">
                  <span className="confirm-warn-text">Delete?</span>
                  <button className="confirm-del-btn yes" onClick={() => onDeleteSession(sessionId)}>Yes</button>
                  <button className="confirm-del-btn no" onClick={() => setConfirmDelete(false)}>No</button>
                </div>
              ) : (
                <button
                  className="delete-session-icon-btn"
                  onClick={() => setConfirmDelete(true)}
                  title="Delete conversation"
                >
                  🗑️
                </button>
              )}
            </>
          )}
        </div>
      </header>

      {/* ------------------------------------------------------------- */}
      {/* MESSAGE STREAM AREA                                           */}
      {/* ------------------------------------------------------------- */}
      <div className="chat-messages-scrollview" ref={chatScrollRef}>
        {/* If no turns in this session yet, show prompt banner */}
        {turns.length === 0 && (
          <div className="empty-chat-welcome">
            <div className="welcome-flame-icon">🔥</div>
            <h3>Conversation Initialized</h3>
            <p>Speak or type anything below to execute tasks, query hardware, or write code.</p>
          </div>
        )}

        {turns.map((turn, idx) => {
          const isUser = turn.role === 'user'
          const timeString = turn.timestamp
            ? new Date(turn.timestamp).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
            : '12:14 AM'

          return (
            <motion.div
              key={turn.id || `turn-${idx}`}
              className={`chat-bubble-row ${isUser ? 'user-align' : 'assistant-align'}`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
            >
              {!isUser && (
                <div className="assistant-avatar-badge">
                  <svg width={20} height={20} viewBox="0 0 24 24" fill="none">
                    <defs>
                      <linearGradient id="avatarGrad" x1="12" y1="2" x2="12" y2="22" gradientUnits="userSpaceOnUse">
                        <stop offset="0%" stopColor="#ffb300" />
                        <stop offset="100%" stopColor="#ff3d00" />
                      </linearGradient>
                    </defs>
                    <path
                      d="M12 2C10.5 4.5 10 6 10 7.5C10 8.5 10.5 9.5 11.5 10C9 9.5 7.5 8 7 6.5C5.5 8.5 5 11 5 13C5 17 8 21 12 21C16 21 19 17 19 13C19 9.5 17.5 6.5 15 4C15 6 14.5 7 13.5 7.5C13.5 6 13 4 12 2Z"
                      fill="url(#avatarGrad)"
                    />
                  </svg>
                </div>
              )}

              <div className="bubble-wrapper">
                {/* User Message */}
                {isUser && (
                  <div className="user-message-bubble">
                    <div className="message-text">{turn.text}</div>
                    <div className="message-meta-row right">
                      <span className="meta-time">{timeString}</span>
                      {turn.source === 'telegram' && <span className="meta-origin">📱 Telegram</span>}
                    </div>
                  </div>
                )}

                {/* Assistant Message */}
                {!isUser && (
                  <div className="assistant-message-bubble">
                    <div className="message-text">
                      {turn.text.includes('```') ? (
                        // Code block rendering
                        <div>
                          {turn.text.split('```').map((part, pIdx) => {
                            if (pIdx % 2 === 1) {
                              const codeLines = part.split('\n')
                              const lang = codeLines[0].trim() || 'python'
                              const code = codeLines.slice(1).join('\n')
                              return (
                                <div key={pIdx} className="code-block-container">
                                  <div className="code-block-header">
                                    <span className="code-lang-label">{lang}</span>
                                    <button
                                      className="code-copy-btn"
                                      onClick={() => handleCopyCode(code, `code-${pIdx}`)}
                                    >
                                      {copiedCodeId === `code-${pIdx}` ? 'Copied! ✓' : 'Copy Code'}
                                    </button>
                                  </div>
                                  <pre className="code-block-pre">
                                    <code>{code}</code>
                                  </pre>
                                </div>
                              )
                            }
                            return <p key={pIdx}>{part}</p>
                          })}
                        </div>
                      ) : (
                        <p>{turn.text}</p>
                      )}
                    </div>

                    {/* Interactive Action Card: Spotify Music */}
                    {(turn.text.toLowerCase().includes('spotify') || turn.text.toLowerCase().includes('lofi') || (turn.tools && turn.tools.includes('spotify'))) && (
                      <div className="rich-action-card spotify-card">
                        <div className="action-card-left">
                          <span className="spotify-icon">🟢</span>
                          <div className="action-card-info">
                            <span className="card-primary-title">Spotify</span>
                            <span className="card-secondary-desc">Playing: Lofi Beats</span>
                          </div>
                        </div>
                        <button
                          className="action-card-btn open"
                          onClick={() => onExecuteToolAction('app_launch', 'spotify')}
                        >
                          Open ↗
                        </button>
                      </div>
                    )}

                    <div className="message-meta-row left">
                      <span className="meta-time">{timeString}</span>
                      {turn.tools && turn.tools.length > 0 && (
                        <div className="tool-chips-row">
                          {turn.tools.map((t) => (
                            <span key={t} className="tool-chip">⚡ {t}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </motion.div>
          )
        })}

        {/* Live HUD Caption Stream from Sarvam Saaras V4 STT */}
        {caption && (
          <motion.div
            className="chat-live-caption-pill"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <span className="caption-pulse-dot" />
            <span className="caption-text">{caption}</span>
          </motion.div>
        )}

        {/* Active Tool Spinner */}
        {activeTool && (
          <div className="chat-tool-execution-bar">
            <span className="tool-spin-indicator" />
            <span>Executing tool: <strong>{activeTool}</strong>...</span>
          </div>
        )}
      </div>
    </div>
  )
}
