import { useMemo } from 'react'
import { motion } from 'framer-motion'

interface Screen04VoiceProps {
  phase: string
  level: number
  caption: string
  onToggleVoice: () => void
  onClose: () => void
}

export function Screen04Voice({
  phase,
  level,
  caption,
  onToggleVoice,
  onClose,
}: Screen04VoiceProps) {
  // Generate 24 animated waveform bars reactive to audio level
  const waveformBars = useMemo(() => {
    return Array.from({ length: 28 }, (_, i) => {
      // Dynamic height based on level + wave factor
      const wave = Math.sin((i / 28) * Math.PI) * 0.8 + 0.2
      const dynamicScale = Math.max(0.12, Math.min(1.0, level * 2.5 * wave + Math.random() * 0.15))
      return dynamicScale
    })
  }, [level])

  const getStatusText = () => {
    switch (phase) {
      case 'listening':
        return 'Listening...'
      case 'thinking':
        return 'Transcribing & Thinking...'
      case 'tooling':
        return 'Executing Tool...'
      case 'speaking':
        return 'Speaking...'
      default:
        return 'Standby'
    }
  }

  return (
    <div className="screen-voice-overlay">
      <div className="voice-stage-container">
        {/* Top Control Bar */}
        <div className="voice-top-header">
          <div className="voice-engine-chips">
            <span className="engine-chip sarvam">⚡ Sarvam Saaras V4 STT</span>
            <span className="engine-chip zira">🔊 Microsoft Zira TTS</span>
          </div>
          <button className="voice-close-icon-btn" onClick={onClose} title="Return to Dashboard">
            ✕
          </button>
        </div>

        {/* Center Mic & Pulsing Ring */}
        <div className="voice-center-visual">
          <div
            className={`voice-reactor-ring ${phase === 'listening' ? 'pulsing-cyan' : phase === 'speaking' ? 'pulsing-orange' : ''}`}
            onClick={onToggleVoice}
            title="Click to toggle mic"
          >
            {/* Outer animated rings */}
            <span
              className="ring-aura-outer"
              style={{ transform: `scale(${1 + Math.min(0.6, level * 1.5)})` }}
            />
            <span
              className="ring-aura-middle"
              style={{ transform: `scale(${1 + Math.min(0.35, level * 0.9)})` }}
            />

            {/* Inner Mic Button */}
            <div className="voice-mic-core">
              <svg width={42} height={42} viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="8" y1="23" x2="16" y2="23" />
              </svg>
            </div>
          </div>

          <h2 className="voice-status-heading">{getStatusText()}</h2>
          <p className="voice-status-sub">
            {phase === 'listening'
              ? 'Say "Phoenix" or ask your question in Hindi, Hinglish, or English'
              : 'Voice recognition neural pipeline active'}
          </p>

          {/* Reactive Waveform Bars */}
          <div className="waveform-visualizer-bar">
            {waveformBars.map((heightScale, idx) => (
              <motion.div
                key={idx}
                className="waveform-bar-col"
                animate={{
                  height: phase === 'listening' || phase === 'speaking' ? `${heightScale * 64}px` : '6px',
                }}
                transition={{ duration: 0.08 }}
              />
            ))}
          </div>

          {/* Live HUD Caption Stream */}
          <div className="voice-transcription-box">
            {caption ? (
              <p className="voice-caption-live">{caption}</p>
            ) : (
              <p className="voice-caption-placeholder">
                {phase === 'listening' ? 'Listening for input...' : 'Microphone ready'}
              </p>
            )}
          </div>
        </div>

        {/* Bottom Actions */}
        <div className="voice-bottom-footer">
          <button className="voice-stop-btn" onClick={onToggleVoice}>
            {phase === 'listening' ? 'Stop Listening' : 'Start Listening'}
          </button>
        </div>
      </div>
    </div>
  )
}
