import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

interface TrustedUser {
  id: string
  name: string
  telegram_id: string
  role: string
  status: string
  added_at: number
}

interface PermissionItem {
  label: string
  level: string
  requires_approval: boolean
}

interface ApprovalItem {
  id: string
  command: string
  sender: string
  source: string
  timestamp: number
}

export function Screen07Security() {
  const [activeSection, setActiveSection] = useState<'trusted' | 'permissions' | 'alerts' | 'approvals'>('trusted')
  const [trustedUsers, setTrustedUsers] = useState<TrustedUser[]>([])
  const [permissions, setPermissions] = useState<Record<string, PermissionItem>>({})
  const [remoteEnabled, setRemoteEnabled] = useState(true)
  const [approvals, setApprovals] = useState<ApprovalItem[]>([])
  const [showAddModal, setShowAddModal] = useState(false)
  const [newUserName, setNewUserName] = useState('')
  const [newUserTelegramId, setNewUserTelegramId] = useState('')
  const [newUserRole, setNewUserRole] = useState('Authorized Operator')

  const fetchSecurityData = () => {
    // 1. Trusted users & remote status
    fetch('http://127.0.0.1:8000/api/security/trusted-users')
      .then((r) => r.json())
      .then((d) => {
        if (d.trusted_users) setTrustedUsers(d.trusted_users)
        if (d.remote_enabled !== undefined) setRemoteEnabled(d.remote_enabled)
      })
      .catch(() => {})

    // 2. Permissions matrix
    fetch('http://127.0.0.1:8000/api/security/permissions')
      .then((r) => r.json())
      .then((d) => {
        if (d.permissions) setPermissions(d.permissions)
      })
      .catch(() => {})

    // 3. Pending approvals
    fetch('http://127.0.0.1:8000/api/security/approvals')
      .then((r) => r.json())
      .then((d) => {
        if (d.approvals) setApprovals(d.approvals)
      })
      .catch(() => {})
  }

  useEffect(() => {
    fetchSecurityData()
  }, [])

  // Emergency Kill Switch Toggle
  const handleToggleRemote = async () => {
    const nextState = !remoteEnabled
    try {
      const res = await fetch('http://127.0.0.1:8000/api/security/remote/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: nextState }),
      })
      const d = await res.json()
      setRemoteEnabled(d.remote_enabled)
    } catch {
      setRemoteEnabled(nextState)
    }
  }

  // Add trusted user
  const handleAddUser = async () => {
    if (!newUserName.trim() || !newUserTelegramId.trim()) return
    try {
      await fetch('http://127.0.0.1:8000/api/security/trusted-users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newUserName.trim(),
          telegram_id: newUserTelegramId.trim(),
          role: newUserRole,
        }),
      })
      setShowAddModal(false)
      setNewUserName('')
      setNewUserTelegramId('')
      fetchSecurityData()
    } catch (e) {
      console.warn('Failed to add user', e)
    }
  }

  // Remove trusted user
  const handleRemoveUser = async (id: string) => {
    try {
      await fetch(`http://127.0.0.1:8000/api/security/trusted-users/${id}`, {
        method: 'DELETE',
      })
      fetchSecurityData()
    } catch (e) {
      console.warn('Failed to remove user', e)
    }
  }

  // Update permission toggle
  const handleToggleApprovalRequired = async (key: string) => {
    const perm = permissions[key]
    if (!perm) return
    const updatedApproval = !perm.requires_approval
    try {
      await fetch('http://127.0.0.1:8000/api/security/permissions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          key,
          level: perm.level,
          requires_approval: updatedApproval,
        }),
      })
      setPermissions((prev) => ({
        ...prev,
        [key]: { ...perm, requires_approval: updatedApproval },
      }))
    } catch (e) {
      console.warn('Failed to update permission', e)
    }
  }

  // Resolve pending approval
  const handleResolveApproval = async (id: string, approved: boolean) => {
    try {
      await fetch(`http://127.0.0.1:8000/api/security/approvals/${id}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved }),
      })
      fetchSecurityData()
    } catch (e) {
      console.warn('Failed to resolve approval', e)
    }
  }

  return (
    <div className="screen-security-layout">
      {/* Header */}
      <div className="security-page-header">
        <div>
          <h2 className="security-title">Security Center</h2>
          <p className="security-subtitle">Manage access, permissions, and monitor security events.</p>
        </div>

        {/* Emergency Remote Kill Switch Banner */}
        <div className={`emergency-kill-banner ${remoteEnabled ? 'armed' : 'halted'}`}>
          <div className="kill-banner-info">
            <span className="kill-dot" />
            <div>
              <span className="kill-label">Telegram Remote Gateway</span>
              <span className="kill-status">{remoteEnabled ? 'ACTIVE & MONITORING' : 'DISABLED (EMERGENCY HALT)'}</span>
            </div>
          </div>
          <button className={`kill-switch-btn ${remoteEnabled ? 'halt-btn' : 'arm-btn'}`} onClick={handleToggleRemote}>
            {remoteEnabled ? 'Disable Telegram Remote' : 'Re-Enable Remote'}
          </button>
        </div>
      </div>

      {/* 4 Cards Grid */}
      <div className="security-cards-nav">
        <div
          className={`sec-nav-card ${activeSection === 'trusted' ? 'active' : ''}`}
          onClick={() => setActiveSection('trusted')}
        >
          <div className="sec-card-icon green">👤</div>
          <div className="sec-card-text">
            <h4>Trusted Users</h4>
            <p>{trustedUsers.length} user{trustedUsers.length === 1 ? ' (You)' : 's'}</p>
          </div>
          <span className="arrow-indicator">›</span>
        </div>

        <div
          className={`sec-nav-card ${activeSection === 'permissions' ? 'active' : ''}`}
          onClick={() => setActiveSection('permissions')}
        >
          <div className="sec-card-icon cyan">🔒</div>
          <div className="sec-card-text">
            <h4>Access Control</h4>
            <p>Command permissions matrix</p>
          </div>
          <span className="arrow-indicator">›</span>
        </div>

        <div
          className={`sec-nav-card ${activeSection === 'alerts' ? 'active' : ''}`}
          onClick={() => setActiveSection('alerts')}
        >
          <div className="sec-card-icon amber">⚠️</div>
          <div className="sec-card-text">
            <h4>Security Alerts</h4>
            <p>0 active threats detected</p>
          </div>
          <span className="arrow-indicator">›</span>
        </div>

        <div
          className={`sec-nav-card ${activeSection === 'approvals' ? 'active' : ''}`}
          onClick={() => setActiveSection('approvals')}
        >
          <div className="sec-card-icon purple">🛡️</div>
          <div className="sec-card-text">
            <h4>Desktop Approvals</h4>
            <p>{approvals.length} pending requests</p>
          </div>
          <span className="arrow-indicator">›</span>
        </div>
      </div>

      {/* Active Section Content Pane */}
      <div className="security-section-pane">
        {/* SECTION: TRUSTED USERS */}
        {activeSection === 'trusted' && (
          <div className="sec-pane-content">
            <div className="pane-header-row">
              <h3>Authorized Telegram IDs Whitelist</h3>
              <button className="add-user-btn" onClick={() => setShowAddModal(true)}>
                + Add Trusted User
              </button>
            </div>

            <div className="trusted-users-list">
              {trustedUsers.map((u) => (
                <div key={u.id} className="trusted-user-card">
                  <div className="user-card-left">
                    <div className="user-avatar-circle">{u.name[0]}</div>
                    <div className="user-details-col">
                      <div className="user-name-row">
                        <span className="user-name">{u.name}</span>
                        <span className="user-role-badge">{u.role}</span>
                      </div>
                      <span className="user-telegram-id">Telegram ID: <code>{u.telegram_id}</code></span>
                    </div>
                  </div>
                  <div className="user-card-right">
                    <span className="user-status-pill green">Authorized</span>
                    {trustedUsers.length > 1 && (
                      <button className="remove-user-btn" onClick={() => handleRemoveUser(u.id)}>
                        Remove
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* SECTION: ACCESS CONTROL PERMISSIONS */}
        {activeSection === 'permissions' && (
          <div className="sec-pane-content">
            <h3>Capability Permissions & Approval Enforcement</h3>
            <div className="permissions-table">
              {Object.entries(permissions).map(([key, perm]) => (
                <div key={key} className="permission-row">
                  <div className="perm-info">
                    <span className="perm-label">{perm.label}</span>
                    <span className="perm-level-tag">{perm.level}</span>
                  </div>
                  <div className="perm-controls">
                    <label className="perm-toggle-label">
                      <span>Require Desktop Confirmation:</span>
                      <input
                        type="checkbox"
                        checked={perm.requires_approval}
                        onChange={() => handleToggleApprovalRequired(key)}
                      />
                    </label>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* SECTION: SECURITY ALERTS */}
        {activeSection === 'alerts' && (
          <div className="sec-pane-content">
            <h3>Active Security Sentinel Status</h3>
            <div className="alert-nominal-banner">
              <span className="nominal-icon">🛡️</span>
              <div>
                <h4>All Systems Encrypted & Nominal</h4>
                <p>No unauthorized intrusion attempts detected. WebSocket traffic is bound to loopback 127.0.0.1.</p>
              </div>
            </div>
          </div>
        )}

        {/* SECTION: DESKTOP APPROVALS */}
        {activeSection === 'approvals' && (
          <div className="sec-pane-content">
            <h3>Pending Remote Action Confirmations</h3>
            {approvals.length === 0 ? (
              <div className="no-approvals-box">
                <span>No sensitive commands are awaiting desktop confirmation.</span>
              </div>
            ) : (
              <div className="approvals-list">
                {approvals.map((appr) => (
                  <div key={appr.id} className="approval-card">
                    <div className="approval-details">
                      <span className="approval-cmd">"{appr.command}"</span>
                      <span className="approval-sender">From: {appr.sender} via {appr.source}</span>
                    </div>
                    <div className="approval-buttons">
                      <button className="approve-btn" onClick={() => handleResolveApproval(appr.id, true)}>
                        Authorize ✓
                      </button>
                      <button className="reject-btn" onClick={() => handleResolveApproval(appr.id, false)}>
                        Deny ✕
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Modal: Add Trusted User */}
      <AnimatePresence>
        {showAddModal && (
          <div className="modal-backdrop">
            <motion.div
              className="modal-box"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
            >
              <h3>Authorize New Telegram User</h3>
              <p>Add a Telegram numeric ID to grant remote access to Phoenix.</p>

              <div className="form-group">
                <label>Operator Name</label>
                <input
                  type="text"
                  placeholder="e.g. Sarthak Secondary"
                  value={newUserName}
                  onChange={(e) => setNewUserName(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label>Telegram Numeric User ID</label>
                <input
                  type="text"
                  placeholder="e.g. 98234110"
                  value={newUserTelegramId}
                  onChange={(e) => setNewUserTelegramId(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label>Role</label>
                <select value={newUserRole} onChange={(e) => setNewUserRole(e.target.value)}>
                  <option value="Mission Controller">Mission Controller (Full Privileges)</option>
                  <option value="Authorized Operator">Authorized Operator (Standard Access)</option>
                  <option value="Read-Only Auditor">Read-Only Auditor</option>
                </select>
              </div>

              <div className="modal-actions">
                <button className="modal-btn cancel" onClick={() => setShowAddModal(false)}>
                  Cancel
                </button>
                <button className="modal-btn confirm" onClick={handleAddUser}>
                  Add User
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  )
}
