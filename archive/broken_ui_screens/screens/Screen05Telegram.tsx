import { useState, useEffect } from 'react'

interface TelegramMessage {
  id: string
  role: 'user' | 'bot'
  text: string
  time_str: string
  lifecycle?: string[]
}

interface Screen05TelegramProps {
  onRefreshActivity: () => void
}

export function Screen05Telegram({ onRefreshActivity }: Screen05TelegramProps) {
  const [messages, setMessages] = useState<TelegramMessage[]>([
    {
      id: 'm1',
      role: 'user',
      text: '/status',
      time_str: '11:42 PM',
    },
    {
      id: 'm2',
      role: 'bot',
      text: '🛡️ Phoenix System Status\nCPU: 24% | RAM: 56%\nGPU: 42% (NVIDIA RTX 3050)\nSystem: Nominal ✓',
      time_str: '11:42 PM',
    },
    {
      id: 'm3',
      role: 'user',
      text: 'open spotify',
      time_str: '11:43 PM',
    },
    {
      id: 'm4',
      role: 'bot',
      text: '🎵 Opened Spotify and initiated playback stream.',
      time_str: '11:43 PM',
    },
  ])

  const [inputCmd, setInputCmd] = useState('')
  const [isExecuting, setIsExecuting] = useState(false)
  const [activeLifecycle, setActiveLifecycle] = useState<string[]>([])
  const [botStatus, setBotStatus] = useState<any>(null)

  const fetchBotStatus = () => {
    fetch('http://127.0.0.1:8000/api/telegram/status')
      .then((r) => r.json())
      .then((d) => setBotStatus(d))
      .catch(() => {})
  }

  useEffect(() => {
    fetchBotStatus()
  }, [])

  const handleSendCommand = async () => {
    if (!inputCmd.trim() || isExecuting) return

    const cmd = inputCmd.trim()
    setInputCmd('')
    setIsExecuting(true)
    setActiveLifecycle(['RECEIVED', 'AUTHENTICATING'])

    const now = new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })

    // Add user message
    const userMsg: TelegramMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      text: cmd,
      time_str: now,
    }
    setMessages((prev) => [...prev, userMsg])

    try {
      const res = await fetch('http://127.0.0.1:8000/api/telegram/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          command: cmd,
          sender_id: '98234110',
          sender_name: 'Sarthak',
        }),
      })

      const data = await res.json()
      if (data.lifecycle) {
        setActiveLifecycle(data.lifecycle)
      }

      const botMsg: TelegramMessage = {
        id: `bot-${Date.now()}`,
        role: 'bot',
        text: data.response || (data.success ? 'Command executed successfully.' : data.error || 'Execution blocked.'),
        time_str: now,
        lifecycle: data.lifecycle,
      }
      setMessages((prev) => [...prev, botMsg])
      onRefreshActivity()
      fetchBotStatus()
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          id: `bot-${Date.now()}`,
          role: 'bot',
          text: '⚠️ Network error: Could not reach Phoenix Gateway server.',
          time_str: now,
        },
      ])
    } finally {
      setIsExecuting(false)
    }
  }

  return (
    <div className="screen-telegram-layout">
      {/* ------------------------------------------------------------- */}
      {/* LEFT PANEL: GATEWAY METRICS & LIFECYCLE MONITOR              */}
      {/* ------------------------------------------------------------- */}
      <div className="telegram-info-panel">
        <h2 className="panel-title">Telegram Remote Control</h2>
        <p className="panel-subtitle">
          Control Phoenix securely from mobile anywhere in the world via Telegram Bot gateway.
        </p>

        {/* Status card */}
        <div className="gateway-status-box">
          <div className="status-metric-row">
            <span className="metric-label">BOT USERNAME</span>
            <span className="metric-val cyan">@Phoenix_sarthak_bot</span>
          </div>
          <div className="status-metric-row">
            <span className="metric-label">GATEWAY STATUS</span>
            <span className="metric-val green">● Connected & Polling</span>
          </div>
          <div className="status-metric-row">
            <span className="metric-label">AUTHORIZED USERS</span>
            <span className="metric-val">1 (Sarthak - ID: 98234110)</span>
          </div>
          <div className="status-metric-row">
            <span className="metric-label">REMOTE EXECUTION</span>
            <span className={`metric-val ${botStatus?.remote_enabled !== false ? 'green' : 'red'}`}>
              {botStatus?.remote_enabled !== false ? 'ENABLED' : 'DISABLED (Kill Switch Active)'}
            </span>
          </div>
        </div>

        {/* 6-Stage Security Lifecycle Visualizer */}
        <div className="lifecycle-card">
          <h4 className="lifecycle-title">Command Security Lifecycle</h4>
          <div className="lifecycle-steps">
            {['RECEIVED', 'AUTHENTICATING', 'AUTHORIZED', 'APPROVED', 'EXECUTING', 'COMPLETED'].map(
              (step, idx) => {
                const isActive = activeLifecycle.includes(step)
                return (
                  <div key={step} className={`lifecycle-step-item ${isActive ? 'active' : ''}`}>
                    <span className="step-num">{idx + 1}</span>
                    <span className="step-name">{step}</span>
                    {isActive && <span className="step-done">✓</span>}
                  </div>
                )
              }
            )}
          </div>
        </div>

        {/* Quick Test Prompt Pills */}
        <div className="quick-test-prompts">
          <span className="quick-test-label">Quick Commands:</span>
          <div className="quick-test-chips">
            <button className="test-chip" onClick={() => setInputCmd('/status')}>
              /status
            </button>
            <button className="test-chip" onClick={() => setInputCmd('open spotify')}>
              open spotify
            </button>
            <button className="test-chip" onClick={() => setInputCmd('lock')}>
              lock workstation
            </button>
            <button className="test-chip" onClick={() => setInputCmd('minimize')}>
              minimize all
            </button>
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------------- */}
      {/* RIGHT PANEL: REALISTIC MOBILE PHONE MOCKUP                    */}
      {/* ------------------------------------------------------------- */}
      <div className="telegram-phone-wrapper">
        <div className="mobile-phone-frame">
          {/* Top Notch / Dynamic Island */}
          <div className="phone-notch">
            <div className="phone-speaker" />
            <div className="phone-camera" />
          </div>

          {/* Telegram Header */}
          <div className="phone-telegram-header">
            <div className="phone-bot-avatar">🤖</div>
            <div className="phone-header-text">
              <span className="phone-bot-name">Phoenix Bot</span>
              <span className="phone-bot-status">bot · online</span>
            </div>
          </div>

          {/* Chat Messages */}
          <div className="phone-messages-area">
            {messages.map((m) => (
              <div key={m.id} className={`phone-bubble-row ${m.role === 'user' ? 'user' : 'bot'}`}>
                <div className="phone-bubble">
                  <div className="bubble-text">{m.text}</div>
                  <span className="bubble-time">{m.time_str} ✓✓</span>
                </div>
              </div>
            ))}

            {isExecuting && (
              <div className="phone-bubble-row bot">
                <div className="phone-bubble thinking">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </div>
              </div>
            )}
          </div>

          {/* Phone Bottom Input Bar */}
          <div className="phone-input-bar">
            <input
              type="text"
              className="phone-text-field"
              placeholder="Message @Phoenix_sarthak_bot..."
              value={inputCmd}
              onChange={(e) => setInputCmd(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSendCommand()}
            />
            <button className="phone-send-btn" onClick={handleSendCommand} disabled={isExecuting}>
              ➤
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
