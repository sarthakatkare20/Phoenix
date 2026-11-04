import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'

interface SystemStats {
  cpu_percent: number
  memory_percent: number
  active_window?: { title: string }
  timestamp?: number
}

interface ActivityItem {
  id: string
  source: string
  action: string
  status: string
  time_str: string
}

interface Screen02HomeProps {
  onVoiceClick: () => void
  onTelegramClick: () => void
  onIDEClick: () => void
  onViewActivityClick: () => void
  isVoiceListening: boolean
  phase: string
  onPowerOn: () => void
}

export function Screen02Home({
  onVoiceClick,
  onTelegramClick,
  onIDEClick,
  onViewActivityClick,
  isVoiceListening,
  phase,
  onPowerOn,
}: Screen02HomeProps) {
  const [stats, setStats] = useState<SystemStats>({
    cpu_percent: 24,
    memory_percent: 56,
  })
  const [recentLogs, setRecentLogs] = useState<ActivityItem[]>([
    { id: '1', source: 'voice', action: 'Open Spotify', status: 'executed', time_str: '12:14 AM' },
    { id: '2', source: 'telegram', action: 'Status check', status: 'verified', time_str: '11:42 AM' },
  ])

  useEffect(() => {
    // Poll system diagnostics
    const fetchSystem = () => {
      fetch('http://127.0.0.1:8000/api/computer/system')
        .then((r) => r.json())
        .then((d) => {
          if (d.system) {
            setStats(d.system)
          }
        })
        .catch(() => {})
    }

    // Fetch recent live activity
    const fetchActivity = () => {
      fetch('http://127.0.0.1:8000/api/activity?limit=3')
        .then((r) => r.json())
        .then((d) => {
          if (d.logs && d.logs.length > 0) {
            setRecentLogs(d.logs.slice(0, 3))
          }
        })
        .catch(() => {})
    }

    fetchSystem()
    fetchActivity()

    const timer = setInterval(() => {
      fetchSystem()
      fetchActivity()
    }, 4000)

    return () => clearInterval(timer)
  }, [])

  return (
    <div className="screen-home-layout">
      {/* ------------------------------------------------------------- */}
      {/* CENTER STAGE HERO (Over 3D Arc Reactor)                       */}
      {/* ------------------------------------------------------------- */}
      <div className="home-center-stage">
        <motion.div
          className="home-hero-content"
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.3 }}
        >
          {/* Flame Icon */}
          <div className="hero-flame-container" onClick={phase === 'offline' ? onPowerOn : undefined}>
            <svg width={64} height={64} viewBox="0 0 24 24" fill="none" className="hero-flame-svg">
              <defs>
                <linearGradient id="heroFlameGlow" x1="12" y1="2" x2="12" y2="22" gradientUnits="userSpaceOnUse">
                  <stop offset="0%" stopColor="#ffb300" />
                  <stop offset="50%" stopColor="#ff6d00" />
                  <stop offset="100%" stopColor="#ff3d00" />
                </linearGradient>
              </defs>
              <path
                d="M12 2C10.5 4.5 10 6 10 7.5C10 8.5 10.5 9.5 11.5 10C9 9.5 7.5 8 7 6.5C5.5 8.5 5 11 5 13C5 17 8 21 12 21C16 21 19 17 19 13C19 9.5 17.5 6.5 15 4C15 6 14.5 7 13.5 7.5C13.5 6 13 4 12 2Z"
                fill="url(#heroFlameGlow)"
              />
              <path
                d="M12 11C11 12 10.5 13 10.5 14C10.5 15.5 11.2 16.5 12 17C12.8 16.5 13.5 15.5 13.5 14C13.5 13 13 12 12 11Z"
                fill="#ffe082"
              />
            </svg>
          </div>

          <h1 className="hero-brand-name">Phoenix</h1>
          <p className="hero-tagline">Your AI Mission Control</p>

          {/* 3 Quick Action Buttons */}
          <div className="hero-quick-actions">
            <button
              className={`hero-action-pill ${isVoiceListening ? 'active-pulse' : ''}`}
              onClick={onVoiceClick}
              title="Activate Voice & STT"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="8" y1="23" x2="16" y2="23" />
              </svg>
              <span>Voice</span>
            </button>

            <button
              className="hero-action-pill"
              onClick={onTelegramClick}
              title="Open Telegram Remote Gateway"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
              <span>Telegram</span>
            </button>

            <button
              className="hero-action-pill"
              onClick={onIDEClick}
              title="Focus Antigravity IDE"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="16 18 22 12 16 6" />
                <polyline points="8 6 2 12 8 18" />
              </svg>
              <span>IDE</span>
            </button>
          </div>

          {phase === 'offline' && (
            <div className="offline-power-banner" onClick={onPowerOn}>
              <span className="power-pulse-ring" />
              <span>Standby — Click to Power Up Reactor & Neural Core</span>
            </div>
          )}
        </motion.div>
      </div>

      {/* ------------------------------------------------------------- */}
      {/* FLOATING RIGHT-SIDE TELEMETRY CARDS                           */}
      {/* ------------------------------------------------------------- */}
      <div className="home-right-widgets">
        {/* System Health Card */}
        <motion.div
          className="widget-card system-health-card"
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.35, delay: 0.1 }}
        >
          <div className="widget-card-header">
            <div className="widget-header-title">
              <span className="widget-icon">⚡</span>
              <span>System Health</span>
            </div>
            <span className="status-live-tag">LIVE</span>
          </div>

          <div className="health-gauges-row">
            {/* CPU Gauge */}
            <div className="circular-metric">
              <div className="metric-ring-wrapper">
                <svg viewBox="0 0 36 36" className="circular-chart cyan">
                  <path
                    className="circle-bg"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                  <path
                    className="circle"
                    strokeDasharray={`${stats.cpu_percent}, 100`}
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                </svg>
                <span className="metric-val-inside">{Math.round(stats.cpu_percent)}%</span>
              </div>
              <span className="metric-name">CPU</span>
            </div>

            {/* GPU Gauge */}
            <div className="circular-metric">
              <div className="metric-ring-wrapper">
                <svg viewBox="0 0 36 36" className="circular-chart teal">
                  <path
                    className="circle-bg"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                  <path
                    className="circle"
                    strokeDasharray="42, 100"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                </svg>
                <span className="metric-val-inside">42%</span>
              </div>
              <span className="metric-name">GPU (RTX 3050)</span>
            </div>

            {/* RAM Gauge */}
            <div className="circular-metric">
              <div className="metric-ring-wrapper">
                <svg viewBox="0 0 36 36" className="circular-chart purple">
                  <path
                    className="circle-bg"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                  <path
                    className="circle"
                    strokeDasharray={`${stats.memory_percent}, 100`}
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                </svg>
                <span className="metric-val-inside">{Math.round(stats.memory_percent)}%</span>
              </div>
              <span className="metric-name">RAM</span>
            </div>
          </div>
        </motion.div>

        {/* Live Activity Card */}
        <motion.div
          className="widget-card live-activity-card"
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.35, delay: 0.2 }}
        >
          <div className="widget-card-header">
            <div className="widget-header-title">
              <span className="widget-icon">⚡</span>
              <span>Live Activity</span>
            </div>
            <span className="activity-badge-count">2 new</span>
          </div>

          <div className="activity-items-list">
            {recentLogs.map((item) => (
              <div key={item.id} className="live-activity-item" onClick={onViewActivityClick}>
                <div className="activity-item-left">
                  <span className="activity-origin-icon">
                    {item.source === 'voice' ? '🎙️' : item.source === 'telegram' ? '📱' : item.source === 'ide' ? '💻' : '⚡'}
                  </span>
                  <div className="activity-details-col">
                    <span className="activity-action-title">
                      {item.source === 'voice'
                        ? 'Voice Command Executed'
                        : item.source === 'telegram'
                        ? 'Telegram Command'
                        : item.source === 'ide'
                        ? 'IDE Action'
                        : 'System Event'}
                    </span>
                    <span className="activity-action-sub">{item.action}</span>
                  </div>
                </div>
                <span className="activity-timestamp">{item.time_str}</span>
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </div>
  )
}
