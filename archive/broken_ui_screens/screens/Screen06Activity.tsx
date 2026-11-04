import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'

interface LogEntry {
  id: string
  timestamp: number
  time_str: string
  source: string
  action: string
  status: string
  details: string
  sender: string
}

export function Screen06Activity() {
  const [filter, setFilter] = useState<'all' | 'voice' | 'telegram' | 'ide' | 'system'>('all')
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(false)

  const fetchLogs = (currentFilter = filter) => {
    setLoading(true)
    fetch(`http://127.0.0.1:8000/api/activity?filter=${currentFilter}&limit=100`)
      .then((r) => r.json())
      .then((d) => {
        if (d.logs) {
          setLogs(d.logs)
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchLogs(filter)
  }, [filter])

  const handleExport = () => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(logs, null, 2))
    const dlAnchor = document.createElement('a')
    dlAnchor.setAttribute('href', dataStr)
    dlAnchor.setAttribute('download', `phoenix_audit_logs_${Date.now()}.json`)
    dlAnchor.click()
  }

  const filteredLogs = logs.filter((l) => {
    if (!searchQuery.trim()) return true
    const q = searchQuery.toLowerCase()
    return (
      l.action.toLowerCase().includes(q) ||
      l.details.toLowerCase().includes(q) ||
      l.sender.toLowerCase().includes(q) ||
      l.source.toLowerCase().includes(q)
    )
  })

  const getSourceIcon = (src: string) => {
    switch (src) {
      case 'voice':
        return '🎙️'
      case 'telegram':
        return '📱'
      case 'ide':
        return '💻'
      default:
        return '⚙️'
    }
  }

  const getStatusBadgeClass = (status: string) => {
    switch (status.toLowerCase()) {
      case 'verified':
        return 'badge-verified'
      case 'completed':
        return 'badge-completed'
      case 'blocked':
        return 'badge-blocked'
      default:
        return 'badge-executed'
    }
  }

  return (
    <div className="screen-activity-layout">
      {/* Header & Controls */}
      <div className="activity-top-controls">
        <div className="controls-left">
          <h2 className="activity-title">Activity & Audit Logs</h2>
          <p className="activity-subtitle">
            Complete telemetry and cryptographic audit trail across Voice, Telegram, IDE, and System actions.
          </p>
        </div>

        <div className="controls-right">
          <input
            type="text"
            className="activity-search-input"
            placeholder="Search audit trail..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <button className="activity-action-btn refresh" onClick={() => fetchLogs(filter)}>
            {loading ? '⟳ Loading...' : '⟳ Refresh'}
          </button>
          <button className="activity-action-btn export" onClick={handleExport}>
            📥 Export JSON
          </button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="activity-filter-tabs">
        {(['all', 'voice', 'telegram', 'ide', 'system'] as const).map((tab) => (
          <button
            key={tab}
            className={`filter-tab-pill ${filter === tab ? 'active' : ''}`}
            onClick={() => setFilter(tab)}
          >
            {tab.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Audit Log Table */}
      <div className="audit-table-card">
        <div className="audit-table-row-header">
          <span>SOURCE</span>
          <span>ACTION / PROMPT</span>
          <span>SENDER</span>
          <span>STATUS</span>
          <span>TIMESTAMP</span>
        </div>

        <div className="audit-table-body">
          {filteredLogs.length === 0 ? (
            <div className="audit-empty-state">
              <span>No logs found for this filter.</span>
            </div>
          ) : (
            filteredLogs.map((entry) => (
              <motion.div
                key={entry.id}
                className="audit-table-row-item"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.15 }}
              >
                <div className="cell-source">
                  <span className="source-icon">{getSourceIcon(entry.source)}</span>
                  <span className="source-label">{entry.source}</span>
                </div>

                <div className="cell-action">
                  <span className="action-text">{entry.action}</span>
                  {entry.details && <span className="action-subdetails">{entry.details}</span>}
                </div>

                <div className="cell-sender">
                  <span className="sender-badge">{entry.sender}</span>
                </div>

                <div className="cell-status">
                  <span className={`status-badge-pill ${getStatusBadgeClass(entry.status)}`}>
                    {entry.status}
                  </span>
                </div>

                <div className="cell-time">
                  <span>{entry.time_str}</span>
                </div>
              </motion.div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
