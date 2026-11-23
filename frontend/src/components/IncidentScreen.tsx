import {useEffect, useState, useCallback, useRef} from 'react'
import axios from 'axios'

interface SimulationState {
  session_id: string
  incident_id: string
  status: string
  target_app: string
  created_at: string
  expires_at: string
  is_active: boolean
}

const STORAGE_KEY = 'cybershield_sim_session'
const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

export default function IncidentScreen() {
  const [session, setSession] = useState<SimulationState | null>(null)
  const [unlocking, setUnlocking] = useState(false)
  const [unlockedSuccess, setUnlockedSuccess] = useState(false)
  const sessionRef = useRef<SimulationState | null>(null)
  sessionRef.current = session

  // 1. Initial detection: Check URL params, localStorage, or cookie
  const checkInitialSession = useCallback(async () => {
    try {
      const urlParams = new URLSearchParams(window.location.search)
      let sessionId = urlParams.get('sim_session')

      if (sessionId) {
        localStorage.setItem(STORAGE_KEY, sessionId)
        // Clean URL query parameter without reloading
        const cleanUrl = window.location.pathname + window.location.hash
        window.history.replaceState({}, document.title, cleanUrl)
      } else {
        sessionId = localStorage.getItem(STORAGE_KEY)
      }

      if (sessionId) {
        // Validate with backend
        const {data} = await axios.get<SimulationState>(`${API_BASE}/simulation/session/${sessionId}`, {
          withCredentials: true,
          timeout: 8000,
        })
        if (data && data.is_active) {
          setSession(data)
          return
        } else {
          localStorage.removeItem(STORAGE_KEY)
          setSession(null)
        }
      }

      // Check if an active session was started for this browser/environment
      const activeRes = await axios.get<{active: boolean; session: SimulationState | null}>(
        `${API_BASE}/simulation/active`,
        {withCredentials: true, timeout: 5000}
      )
      if (activeRes.data.active && activeRes.data.session) {
        localStorage.setItem(STORAGE_KEY, activeRes.data.session.session_id)
        setSession(activeRes.data.session)
      }
    } catch {
      // Backend unreachable or offline; preserve local session if stored
      const localId = localStorage.getItem(STORAGE_KEY)
      if (localId && !sessionRef.current) {
        setSession({
          session_id: localId,
          incident_id: 'INC-SIM-ACTIVE',
          status: 'active',
          target_app: 'CyberShield',
          created_at: new Date().toISOString(),
          expires_at: new Date(Date.now() + 1800000).toISOString(),
          is_active: true,
        })
      }
    }
  }, [])

  useEffect(() => {
    checkInitialSession()
  }, [checkInitialSession])

  // Periodic polling to check if administrator terminated or expired the session
  useEffect(() => {
    if (!session || !session.session_id || unlockedSuccess) return
    const interval = window.setInterval(async () => {
      try {
        const {data} = await axios.get<SimulationState>(
          `${API_BASE}/simulation/session/${session.session_id}`,
          {withCredentials: true, timeout: 5000}
        )
        if (!data || !data.is_active) {
          localStorage.removeItem(STORAGE_KEY)
          setSession(null)
        }
      } catch {
        // Ignore background polling errors
      }
    }, 3000)

    return () => window.clearInterval(interval)
  }, [session, unlockedSuccess])

  // Prevent background scrolling while incident overlay is active
  useEffect(() => {
    if (session && !unlockedSuccess) {
      document.body.style.overflow = 'hidden'
      return () => {
        document.body.style.overflow = ''
      }
    }
  }, [session, unlockedSuccess])

  // 2. Presentation Unlock: Listen for key '0'
  const handleUnlock = useCallback(async () => {
    if (!sessionRef.current || unlocking) return
    setUnlocking(true)
    try {
      await axios.post(
        `${API_BASE}/simulation/unlock`,
        {session_id: sessionRef.current.session_id},
        {withCredentials: true, timeout: 10000}
      )
      setUnlockedSuccess(true)
      localStorage.removeItem(STORAGE_KEY)

      // Graceful visual fade-out before removing overlay
      window.setTimeout(() => {
        setSession(null)
        setUnlockedSuccess(false)
        setUnlocking(false)
      }, 950)
    } catch {
      // Fallback: unlock locally if backend failed to respond
      setUnlockedSuccess(true)
      localStorage.removeItem(STORAGE_KEY)
      window.setTimeout(() => {
        setSession(null)
        setUnlockedSuccess(false)
        setUnlocking(false)
      }, 950)
    }
  }, [unlocking])

  useEffect(() => {
    if (!session || unlockedSuccess) return

    const onKeyDown = (event: KeyboardEvent) => {
      // Detect the key '0'
      if (event.key === '0' || event.code === 'Digit0' || event.code === 'Numpad0') {
        event.preventDefault()
        event.stopPropagation()
        handleUnlock()
      }
    }

    window.addEventListener('keydown', onKeyDown, {capture: true})
    return () => window.removeEventListener('keydown', onKeyDown, {capture: true})
  }, [session, unlockedSuccess, handleUnlock])

  if (!session) return null

  return (
    <div
      id="cybershield-incident-overlay"
      className={`cs-incident-root ${unlockedSuccess ? 'cs-incident-dismissing' : ''}`}
      role="alertdialog"
      aria-modal="true"
      aria-label="Security Incident Notice"
    >
      <div className="cs-incident-backdrop" />

      <div className="cs-incident-window">
        {/* ================= A. LEFT SIDEBAR ================= */}
        <aside className="cs-incident-sidebar">
          {/* 1. Large Security Lock Illustration */}
          <div className="cs-lock-container">
            <div className="cs-lock-badge">
              <svg
                className="cs-lock-icon"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                <circle cx="12" cy="16" r="1.5" fill="currentColor" />
              </svg>
            </div>
          </div>

          {/* 2. Incident Status Card */}
          <div className="cs-sidebar-card cs-card-status">
            <div className="cs-status-label">SECURITY INCIDENT</div>
            <div className="cs-status-value">
              <span className={`cs-pulse-indicator ${unlockedSuccess ? 'cs-pulse-recovered' : ''}`} />
              {unlockedSuccess ? 'ACCESS RESTORED' : 'ACCESS RESTRICTED'}
            </div>
          </div>

          {/* 3. Incident Information */}
          <div className="cs-sidebar-card cs-card-info">
            <div className="cs-info-row">
              <span className="cs-info-key">INCIDENT ID</span>
              <span className="cs-info-val cs-code-text">{session.incident_id}</span>
            </div>
            <div className="cs-info-row">
              <span className="cs-info-key">APPLICATION</span>
              <span className="cs-info-val">CyberShield</span>
            </div>
            <div className="cs-info-row">
              <span className="cs-info-key">CATEGORY</span>
              <span className="cs-info-val">Access Restriction</span>
            </div>
            <div className="cs-info-row">
              <span className="cs-info-key">SYSTEM STATE</span>
              <span className={`cs-info-val ${unlockedSuccess ? 'cs-text-recovered' : 'cs-text-alert'}`}>
                {unlockedSuccess ? 'Restored' : 'Active'}
              </span>
            </div>
          </div>

          {/* 4. System Status Card */}
          <div className="cs-sidebar-card cs-card-integrity">
            <div className="cs-card-subhead">SYSTEM INTEGRITY MONITOR</div>
            <div className="cs-integrity-indicator">
              <div className="cs-integrity-bar">
                <div className={`cs-integrity-fill ${unlockedSuccess ? 'cs-fill-green' : ''}`} />
              </div>
              <span className="cs-integrity-caption">
                {unlockedSuccess ? 'Integrity Verification Passed' : 'Active Protocol Enforcement'}
              </span>
            </div>
          </div>
        </aside>

        {/* ================= B. MAIN CONTENT AREA ================= */}
        <section className="cs-incident-main">
          {/* Header Banner */}
          <header className="cs-incident-head">
            <div className="cs-kicker-badge">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
              <span>SECURITY PROTOCOL ENFORCED</span>
            </div>
            <h1 className="cs-title">Your System Has Been Locked</h1>
            <p className="cs-subtitle">Security Incident Detected</p>
          </header>

          {/* White / Light-Grey Central Content Panel */}
          <div className="cs-panel-body">
            {/* Section 1: What Happened? */}
            <div className="cs-panel-section">
              <h2 className="cs-sec-title">What Happened?</h2>
              <p className="cs-sec-text">
                A security incident simulation has been activated and access to the CyberShield
                application has temporarily been restricted. All interaction channels, coursework portals,
                and administrative services have been suspended under centralized incident mitigation policy.
              </p>
            </div>

            {/* Section 2: Incident Details */}
            <div className="cs-panel-section">
              <h2 className="cs-sec-title">Incident Details</h2>
              <div className="cs-grid-details">
                <div className="cs-detail-box">
                  <span className="cs-d-key">Incident ID</span>
                  <span className="cs-d-val cs-code-text">{session.incident_id}</span>
                </div>
                <div className="cs-detail-box">
                  <span className="cs-d-key">Target Application</span>
                  <span className="cs-d-val">CyberShield Student Portal</span>
                </div>
                <div className="cs-detail-box">
                  <span className="cs-d-key">Incident Category</span>
                  <span className="cs-d-val">Security Access Incident</span>
                </div>
                <div className="cs-detail-box">
                  <span className="cs-d-key">Session Reference</span>
                  <span className="cs-d-val cs-code-text">{session.session_id.substring(0, 18)}...</span>
                </div>
                <div className="cs-detail-box">
                  <span className="cs-d-key">Current Incident Status</span>
                  <span className={`cs-d-val ${unlockedSuccess ? 'cs-tag-success' : 'cs-tag-warning'}`}>
                    {unlockedSuccess ? 'UNLOCKED / RESTORED' : 'ACTIVE RESTRICTION'}
                  </span>
                </div>
              </div>
            </div>

            {/* Section 3: Security Assessment */}
            <div className="cs-panel-section">
              <h2 className="cs-sec-title">Security Assessment</h2>
              <div className="cs-assessment-list">
                <div className="cs-assess-item">
                  <div className="cs-assess-bullet cs-bullet-red" />
                  <span className="cs-assess-name">Application access:</span>
                  <span className="cs-assess-val">Restricted</span>
                </div>
                <div className="cs-assess-item">
                  <div className="cs-assess-bullet cs-bullet-red" />
                  <span className="cs-assess-name">Session status:</span>
                  <span className="cs-assess-val">Active</span>
                </div>
                <div className="cs-assess-item">
                  <div className="cs-assess-bullet cs-bullet-yellow" />
                  <span className="cs-assess-name">Security response:</span>
                  <span className="cs-assess-val">Pending recovery</span>
                </div>
                <div className="cs-assess-item">
                  <div className="cs-assess-bullet cs-bullet-blue" />
                  <span className="cs-assess-name">Browser session:</span>
                  <span className="cs-assess-val">Protected by simulation state</span>
                </div>
              </div>
            </div>

            {/* Section 4: Recovery Information */}
            <div className="cs-panel-section cs-recovery-section">
              <h2 className="cs-sec-title">Recovery Information</h2>
              <p className="cs-sec-text">
                This application is protected under an authorized demonstration protocol. Normal operation
                can be restored through the designated authorization recovery mechanism once security conditions
                are verified by the presentation operator.
              </p>
              {unlocking && (
                <div className="cs-unlocking-notice">
                  <span className="cs-spinner" />
                  <span>Verifying recovery authorization sequence...</span>
                </div>
              )}
            </div>
          </div>

          {/* ================= C. BOTTOM STATUS BAR ================= */}
          <footer className="cs-incident-footer">
            <div className="cs-footer-left">
              <span className="cs-footer-item">
                <span className="cs-muted">REF:</span> {session.incident_id}
              </span>
              <span className="cs-footer-divider">|</span>
              <span className="cs-footer-item">
                <span className="cs-muted">TARGET:</span> CYBERSHIELD
              </span>
              <span className="cs-footer-divider">|</span>
              <span className="cs-footer-item">
                <span className="cs-muted">STATUS:</span>{' '}
                <strong className={unlockedSuccess ? 'cs-text-recovered' : 'cs-text-alert'}>
                  {unlockedSuccess ? 'RECOVERED' : 'SIMULATION_ACTIVE'}
                </strong>
              </span>
            </div>
            <div className="cs-footer-right">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
              <span>SENTINEL AI PROTOCOL</span>
            </div>
          </footer>
        </section>
      </div>
    </div>
  )
}
