import { useState, useEffect } from 'react'

export function Screen08Settings() {
  const [activeCategory, setActiveCategory] = useState<
    'general' | 'ai_model' | 'voice_tts' | 'stt' | 'telegram' | 'ide' | 'system'
  >('general')

  const [settings, setSettings] = useState<any>({
    general: {
      startup_on_boot: true,
      wake_word: 'Phoenix',
      theme: 'Dark (Teal)',
      language: 'English (US)',
    },
    ai_model: {
      primary_model: 'Google Gemini 2.0 Flash',
      model_id: 'gemini-2.0-flash',
      temperature: 0.7,
      streaming: true,
    },
    voice_tts: {
      engine: 'Microsoft Zira (Desktop)',
      voice_name: 'Microsoft Zira - English (United States)',
      rate: 1.0,
      pitch: 1.0,
    },
    stt: {
      provider: 'Sarvam Saaras V4 (Active)',
      language_code: 'hi-IN',
      support_mixed_hinglish: true,
      configured: true,
    },
    telegram: {
      bot_username: '@Phoenix_sarthak_bot',
      remote_control_enabled: true,
      notify_on_connect: true,
      allowed_users_only: true,
    },
    ide: {
      workspace_root: 'F:\\Phoenix',
      port: 5173,
      antigravity_focus: true,
    },
    system: {
      monitoring_interval_sec: 3,
      gpu_monitor: 'NVIDIA RTX 3050 Laptop GPU (6GB VRAM)',
      emergency_halt: false,
    },
  })

  const [savedNote, setSavedNote] = useState<string | null>(null)

  useEffect(() => {
    fetch('http://127.0.0.1:8000/api/settings/all')
      .then((r) => r.json())
      .then((d) => {
        if (d && Object.keys(d).length > 0) {
          setSettings(d)
        }
      })
      .catch(() => {})
  }, [])

  const handleUpdate = async (category: string, key: string, value: any) => {
    const updatedCategory = {
      ...settings[category],
      [key]: value,
    }

    setSettings((prev: any) => ({
      ...prev,
      [category]: updatedCategory,
    }))

    try {
      await fetch('http://127.0.0.1:8000/api/settings/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          category,
          updates: { [key]: value },
        }),
      })
      setSavedNote('Settings saved ✓')
      setTimeout(() => setSavedNote(null), 2500)
    } catch (e) {
      console.warn('Settings save failed', e)
    }
  }

  const handleTestTTS = async () => {
    try {
      await fetch('http://127.0.0.1:8000/api/tts/speak', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'Phoenix voice synthesizer online. All audio subsystems functioning nominally.' }),
      })
    } catch {}
  }

  return (
    <div className="screen-settings-layout">
      {/* Sub-navigation Sidebar */}
      <div className="settings-subnav">
        <h3 className="subnav-header">Settings</h3>
        <nav className="subnav-list">
          <button
            className={`subnav-item ${activeCategory === 'general' ? 'active' : ''}`}
            onClick={() => setActiveCategory('general')}
          >
            <span>⚙️ General</span>
          </button>
          <button
            className={`subnav-item ${activeCategory === 'ai_model' ? 'active' : ''}`}
            onClick={() => setActiveCategory('ai_model')}
          >
            <span>🧠 AI Model</span>
          </button>
          <button
            className={`subnav-item ${activeCategory === 'voice_tts' ? 'active' : ''}`}
            onClick={() => setActiveCategory('voice_tts')}
          >
            <span>🔊 Voice & TTS</span>
          </button>
          <button
            className={`subnav-item ${activeCategory === 'stt' ? 'active' : ''}`}
            onClick={() => setActiveCategory('stt')}
          >
            <span>🎙️ Speech-to-Text (STT)</span>
          </button>
          <button
            className={`subnav-item ${activeCategory === 'telegram' ? 'active' : ''}`}
            onClick={() => setActiveCategory('telegram')}
          >
            <span>📱 Telegram</span>
          </button>
          <button
            className={`subnav-item ${activeCategory === 'ide' ? 'active' : ''}`}
            onClick={() => setActiveCategory('ide')}
          >
            <span>💻 IDE / Coding</span>
          </button>
          <button
            className={`subnav-item ${activeCategory === 'system' ? 'active' : ''}`}
            onClick={() => setActiveCategory('system')}
          >
            <span>⚡ System</span>
          </button>
        </nav>
      </div>

      {/* Main Settings Form Pane */}
      <div className="settings-content-pane">
        <div className="pane-header-row">
          <h2 className="settings-pane-title">
            {activeCategory === 'general' && 'General Configuration'}
            {activeCategory === 'ai_model' && 'AI Brain & Reasoning Models'}
            {activeCategory === 'voice_tts' && 'Voice Synthesis (TTS)'}
            {activeCategory === 'stt' && 'Speech-to-Text & Sarvam Saaras V4'}
            {activeCategory === 'telegram' && 'Telegram Remote Bot Gateway'}
            {activeCategory === 'ide' && 'Antigravity IDE Integration'}
            {activeCategory === 'system' && 'System Telemetry & Hardware'}
          </h2>
          {savedNote && <span className="settings-saved-pill">{savedNote}</span>}
        </div>

        {/* GENERAL SETTINGS */}
        {activeCategory === 'general' && (
          <div className="settings-form-group">
            <div className="form-item-row">
              <div>
                <span className="item-title">Run Phoenix on System Startup</span>
                <p className="item-desc">Launch AI Mission Control automatically when Windows boots</p>
              </div>
              <input
                type="checkbox"
                checked={settings.general?.startup_on_boot ?? true}
                onChange={(e) => handleUpdate('general', 'startup_on_boot', e.target.checked)}
              />
            </div>

            <div className="form-item-row">
              <div>
                <span className="item-title">Wake Word</span>
                <p className="item-desc">Primary vocative to wake voice recognition</p>
              </div>
              <input
                type="text"
                className="text-setting-input"
                value={settings.general?.wake_word ?? 'Phoenix'}
                onChange={(e) => handleUpdate('general', 'wake_word', e.target.value)}
              />
            </div>

            <div className="form-item-row">
              <div>
                <span className="item-title">Interface Theme</span>
                <p className="item-desc">Visual styling and colorway</p>
              </div>
              <select
                className="select-setting-input"
                value={settings.general?.theme ?? 'Dark (Teal)'}
                onChange={(e) => handleUpdate('general', 'theme', e.target.value)}
              >
                <option value="Dark (Teal)">Dark (Teal / Cyan Glow)</option>
                <option value="Cinematic Deep Black">Cinematic Deep Black</option>
                <option value="Jarvis Holographic">Jarvis Holographic</option>
              </select>
            </div>

            <div className="form-item-row">
              <div>
                <span className="item-title">Primary Language</span>
                <p className="item-desc">Default language comprehension and synthesis</p>
              </div>
              <select
                className="select-setting-input"
                value={settings.general?.language ?? 'English (US)'}
                onChange={(e) => handleUpdate('general', 'language', e.target.value)}
              >
                <option value="English (US)">English (US)</option>
                <option value="Hindi & Hinglish">Hindi & Hinglish (Sarvam Saaras V4)</option>
              </select>
            </div>
          </div>
        )}

        {/* AI MODEL SETTINGS */}
        {activeCategory === 'ai_model' && (
          <div className="settings-form-group">
            <div className="form-item-row">
              <div>
                <span className="item-title">Primary Reflex Model</span>
                <p className="item-desc">Ultra-fast sub-300ms intelligence engine</p>
              </div>
              <span className="badge-highlight purple">Google Gemini 2.0 Flash</span>
            </div>

            <div className="form-item-row">
              <div>
                <span className="item-title">Temperature ({settings.ai_model?.temperature ?? 0.7})</span>
                <p className="item-desc">Controls creativity vs determinism in reasoning</p>
              </div>
              <input
                type="range"
                min="0.1"
                max="1.0"
                step="0.05"
                value={settings.ai_model?.temperature ?? 0.7}
                onChange={(e) => handleUpdate('ai_model', 'temperature', parseFloat(e.target.value))}
              />
            </div>

            <div className="form-item-row">
              <div>
                <span className="item-title">Token Streaming</span>
                <p className="item-desc">Stream responses in real time with progressive TTS generation</p>
              </div>
              <input
                type="checkbox"
                checked={settings.ai_model?.streaming ?? true}
                onChange={(e) => handleUpdate('ai_model', 'streaming', e.target.checked)}
              />
            </div>
          </div>
        )}

        {/* VOICE & TTS SETTINGS */}
        {activeCategory === 'voice_tts' && (
          <div className="settings-form-group">
            <div className="form-item-row">
              <div>
                <span className="item-title">Voice Synthesis Engine</span>
                <p className="item-desc">Speech generation provider on Windows</p>
              </div>
              <span className="badge-highlight purple">Microsoft Zira (Desktop - 100% Offline)</span>
            </div>

            <div className="form-item-row">
              <div>
                <span className="item-title">Speech Rate ({settings.voice_tts?.rate ?? 1.0}x)</span>
                <p className="item-desc">Playback speed for voice responses</p>
              </div>
              <input
                type="range"
                min="0.5"
                max="1.5"
                step="0.1"
                value={settings.voice_tts?.rate ?? 1.0}
                onChange={(e) => handleUpdate('voice_tts', 'rate', parseFloat(e.target.value))}
              />
            </div>

            <div className="form-item-row">
              <div>
                <span className="item-title">Test Speech Output</span>
                <p className="item-desc">Play a test sentence through the active TTS speaker</p>
              </div>
              <button className="test-voice-btn" onClick={handleTestTTS}>
                🔊 Test Voice
              </button>
            </div>
          </div>
        )}

        {/* STT SETTINGS */}
        {activeCategory === 'stt' && (
          <div className="settings-form-group">
            <div className="form-item-row">
              <div>
                <span className="item-title">STT Provider</span>
                <p className="item-desc">Deep Hinglish and Indian accent recognition</p>
              </div>
              <span className="badge-highlight green">Sarvam Saaras V4 (Active)</span>
            </div>

            <div className="form-item-row">
              <div>
                <span className="item-title">Language Code</span>
                <p className="item-desc">Speech recognition dialect mode</p>
              </div>
              <span className="badge-highlight cyan">hi-IN (Auto Hinglish)</span>
            </div>

            <div className="form-item-row">
              <div>
                <span className="item-title">Mixed-Language Speech Support</span>
                <p className="item-desc">Automatic comprehension of Hindi + English combined sentences</p>
              </div>
              <span className="badge-highlight green">Enabled ✓</span>
            </div>
          </div>
        )}

        {/* TELEGRAM SETTINGS */}
        {activeCategory === 'telegram' && (
          <div className="settings-form-group">
            <div className="form-item-row">
              <div>
                <span className="item-title">Bot Handle</span>
                <p className="item-desc">Official mobile gateway bot on Telegram</p>
              </div>
              <span className="badge-highlight cyan">@Phoenix_sarthak_bot</span>
            </div>

            <div className="form-item-row">
              <div>
                <span className="item-title">Remote Control Gateway</span>
                <p className="item-desc">Allow remote task dispatching from Telegram</p>
              </div>
              <input
                type="checkbox"
                checked={settings.telegram?.remote_control_enabled ?? true}
                onChange={(e) => handleUpdate('telegram', 'remote_control_enabled', e.target.checked)}
              />
            </div>
          </div>
        )}

        {/* IDE SETTINGS */}
        {activeCategory === 'ide' && (
          <div className="settings-form-group">
            <div className="form-item-row">
              <div>
                <span className="item-title">Workspace Directory</span>
                <p className="item-desc">Active project folder path</p>
              </div>
              <span className="badge-highlight cyan">{settings.ide?.workspace_root ?? 'F:\\Phoenix'}</span>
            </div>

            <div className="form-item-row">
              <div>
                <span className="item-title">Vite Dev Server Port</span>
                <p className="item-desc">Local frontend runtime port</p>
              </div>
              <span className="badge-highlight cyan">5173</span>
            </div>
          </div>
        )}

        {/* SYSTEM SETTINGS */}
        {activeCategory === 'system' && (
          <div className="settings-form-group">
            <div className="form-item-row">
              <div>
                <span className="item-title">Hardware Telemetry Polling</span>
                <p className="item-desc">Frequency of CPU, RAM, and GPU status queries</p>
              </div>
              <span className="badge-highlight cyan">Every 3 seconds</span>
            </div>

            <div className="form-item-row">
              <div>
                <span className="item-title">GPU Acceleration</span>
                <p className="item-desc">Dedicated hardware GPU accelerator</p>
              </div>
              <span className="badge-highlight green">NVIDIA RTX 3050 Laptop GPU (6GB VRAM)</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
