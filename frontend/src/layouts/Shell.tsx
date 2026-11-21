import {useEffect, useState} from 'react'
import {Activity, BookOpen, ClipboardList, LayoutDashboard, LogOut, Menu, Moon, PanelLeftClose, Settings, Sun, UserRound, Users, X} from 'lucide-react'
import {Link, NavLink, Outlet, useLocation} from 'react-router-dom'
import {describe} from '../api'
import {useAuth, usePreferences} from '../context'
import {Brand, Failure, initials} from '../components/ui'

export default function Shell() {
  const auth = useAuth()
  const {theme, setTheme} = usePreferences()
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const location = useLocation()
  const user = auth.user!
  const admin = user.role === 'admin'
  const navigation = [
    {to: '/', text: 'Dashboard', Icon: LayoutDashboard},
    {to: '/courses', text: 'Courses', Icon: BookOpen},
    {to: '/assignments', text: 'Assignments', Icon: ClipboardList},
    ...(admin ? [{to: '/students', text: 'Students', Icon: Users}] : []),
    {to: '/profile', text: admin ? 'Profile' : 'Student Profile', Icon: UserRound},
    {to: '/activity', text: 'Activity History', Icon: Activity},
    {to: '/settings', text: 'Settings', Icon: Settings},
  ]
  const current = navigation.find(item => item.to === '/' ? location.pathname === '/' :
    location.pathname.startsWith(item.to))?.text ?? 'Portal'

  useEffect(() => { setMobileOpen(false) }, [location.pathname])

  async function logout() {
    setError('')
    setBusy(true)
    try { await auth.signOut() } catch (problem) { setError(describe(problem)) } finally {setBusy(false)}
  }

  return <div className={'shell' + (collapsed ? ' collapsed' : '') + (mobileOpen ? ' mobile-open' : '')}
    onKeyDown={event => { if (event.key === 'Escape') setMobileOpen(false) }}>
    <a className="skip" href="#content">Skip to content</a>
    {mobileOpen && <button type="button" className="sidebar-overlay" aria-label="Close menu" onClick={() => setMobileOpen(false)}/>}
    <aside className="sidebar" id="navigation">
      <Link to="/" className="brand-link"><Brand/></Link>
      <nav aria-label="Main navigation">
        <p className="nav-title">WORKSPACE</p>
        {navigation.map(({to, text, Icon}) => <NavLink key={to} to={to} end={to === '/'} title={collapsed ? text : undefined}
          className="nav-entry"><Icon size={19}/><span>{text}</span></NavLink>)}
      </nav>
      <div className="sidebar-bottom">
        <button type="button" onClick={logout} disabled={busy} title="Sign out" className="nav-entry signout">
          <LogOut size={19}/><span>{busy ? 'Signing out…' : 'Logout'}</span>
        </button>
        <div className="side-user"><span className="avatar">{initials(user.full_name)}</span><div>
          <strong>{user.full_name}</strong><small>{admin ? 'Administrator' : 'Student account'}</small>
        </div></div>
      </div>
    </aside>
    <div className="workspace">
      <header className="topbar">
        <div className="flex items-center gap-3">
          <button type="button" className="icon-button desktop-toggle" aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-controls="navigation" aria-expanded={!collapsed} onClick={() => setCollapsed(!collapsed)}><PanelLeftClose size={19}/></button>
          <button type="button" className="icon-button mobile-toggle" aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
            aria-controls="navigation" aria-expanded={mobileOpen} onClick={() => setMobileOpen(!mobileOpen)}>
            {mobileOpen ? <X size={21}/> : <Menu size={21}/>}
          </button>
          <div className="breadcrumb"><span>Workspace</span><span aria-hidden="true">/</span><strong>{current}</strong></div>
        </div>
        <div className="top-actions">
          <button type="button" className="icon-button" aria-label="Toggle color theme"
            onClick={() => setTheme(theme === 'dark' || (theme === 'system' && document.documentElement.dataset.theme === 'dark') ? 'light' : 'dark')}>
            <Sun className="theme-sun" size={19}/><Moon className="theme-moon" size={19}/>
          </button>
          <Link to="/profile" className="avatar" aria-label="Open your profile">{initials(user.full_name)}</Link>
        </div>
      </header>
      <main className="content" id="content" tabIndex={-1}>{error && <Failure message={error}/>}<Outlet/></main>
    </div>
  </div>
}
