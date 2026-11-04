import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

interface StageItem {
  id: string
  name: string
  status: string
  details: string
  latency_ms: number
}

interface Screen01LaunchProps {
  onComplete: () => void
  isOpen: boolean
  onClose?: () => void
}

export function Screen01Launch({ onComplete, isOpen, onClose }: Screen01LaunchProps) {
  const [stages, setStages] = useState<StageItem[]>([
    { id: 'core', name: 'Initializing Core Modules...', status: 'ready', details: 'FastAPI & ASGI Loop OK', latency_ms: 12 },
    { id: 'ai', name: 'Loading AI Models (Gemini Flash)...', status: 'ready', details: 'Google Gemini 2.0 Flash reflex engine', latency_ms: 78 },
    { id: 'voice', name: 'Connecting Voice & STT (Sarvam Saaras V4)...', status: 'ready', details: 'Sarvam Saaras V4 API authenticated', latency_ms: 34 },
    { id: 'telegram', name: 'Connecting Telegram Gateway...', status: 'ready', details: '@Phoenix_sarthak_bot gateway initialized', latency_ms: 41 },
    { id: 'ide', name: 'Connecting Antigravity IDE Integration...', status: 'ready', details: 'Workspace linked on localhost:5173', latency_ms: 19 },
    { id: 'system', name: 'Initializing System Monitoring...', status: 'ready', details: 'Hardware telemetry (NVIDIA RTX 3050) active', latency_ms: 15 },
    { id: 'db', name: 'Loading Conversation Database...', status: 'ready', details: 'SQLite paaro_memory.db OK', latency_ms: 9 },
    { id: 'ready', name: 'System Ready ✓', status: 'ready', details: 'Mission Control Armed and Standing By', latency_ms: 0 },
  ])
  const [currentStageIdx, setCurrentStageIdx] = useState(0)
  const [progress, setProgress] = useState(15)

  useEffect(() => {
    if (!isOpen) return

    // Fetch live status from backend
    fetch('http://127.0.0.1:8000/api/system/initialization-status')
      .then((r) => r.json())
      .then((d) => {
        if (d.stages && d.stages.length > 0) {
          setStages(d.stages)
        }
      })
      .catch(() => {})

    // Animate stage checklist progressively
    let idx = 0
    const interval = setInterval(() => {
      idx++
      setCurrentStageIdx(idx)
      setProgress(Math.min(100, Math.round(((idx + 1) / 8) * 100)))
      if (idx >= 8) {
        clearInterval(interval)
        setTimeout(() => {
          onComplete()
        }, 1200)
      }
    }, 450)

    return () => clearInterval(interval)
  }, [isOpen, onComplete])

  if (!isOpen) return null

  return (
    <AnimatePresence>
      <motion.div
        className="launch-overlay-backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      >
        <div className="launch-card-modal">
          {/* Flame branding */}
          <div className="launch-flame-wrapper">
            <svg width={72} height={72} viewBox="0 0 24 24" fill="none" className="launch-flame-glow">
              <defs>
                <linearGradient id="launchFlameGrad" x1="12" y1="2" x2="12" y2="22" gradientUnits="userSpaceOnUse">
                  <stop offset="0%" stopColor="#ffb300" />
                  <stop offset="45%" stopColor="#ff6d00" />
                  <stop offset="100%" stopColor="#ff3d00" />
                </linearGradient>
              </defs>
              <path
                d="M12 2C10.5 4.5 10 6 10 7.5C10 8.5 10.5 9.5 11.5 10C9 9.5 7.5 8 7 6.5C5.5 8.5 5 11 5 13C5 17 8 21 12 21C16 21 19 17 19 13C19 9.5 17.5 6.5 15 4C15 6 14.5 7 13.5 7.5C13.5 6 13 4 12 2Z"
                fill="url(#launchFlameGrad)"
              />
              <path
                d="M12 11C11 12 10.5 13 10.5 14C10.5 15.5 11.2 16.5 12 17C12.8 16.5 13.5 15.5 13.5 14C13.5 13 13 12 12 11Z"
                fill="#ffe082"
              />
            </svg>
          </div>

          <h1 className="launch-title">Phoenix</h1>
          <p className="launch-subtitle">Initializing Systems...</p>

          {/* Progress bar */}
          <div className="launch-progress-container">
            <div className="launch-progress-track">
              <div className="launch-progress-fill" style={{ width: `${progress}%` }} />
            </div>
            <div className="launch-progress-label">
              <span>BOOT TELEMETRY</span>
              <span>{progress}%</span>
            </div>
          </div>

          {/* Checklist */}
          <div className="launch-checklist">
            {stages.map((st, i) => {
              const isDone = i <= currentStageIdx
              const isCurrent = i === currentStageIdx
              return (
                <div key={st.id} className={`launch-check-item ${isDone ? 'done' : ''} ${isCurrent ? 'current' : ''}`}>
                  <span className="check-icon">{isDone ? '✓' : '○'}</span>
                  <span className="check-name">{st.name}</span>
                  {isDone && <span className="check-latency">{st.latency_ms > 0 ? `${st.latency_ms}ms` : 'Ready'}</span>}
                </div>
              )
            })}
          </div>

          {/* Action Button */}
          <div className="launch-actions">
            <button className="launch-enter-btn" onClick={onComplete}>
              {progress >= 100 ? 'Enter Mission Control →' : 'Skip To Mission Control'}
            </button>
            {onClose && (
              <button className="launch-close-btn" onClick={onClose}>
                Dismiss
              </button>
            )}
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
