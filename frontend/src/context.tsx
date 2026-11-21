import {createContext, useContext, useEffect, useState, type ReactNode} from 'react'
import {api, setCsrf, statusOf, type Session} from './api'
import type {User} from './types'

type Theme = 'light' | 'dark' | 'system'
type Auth = {
  user: User | null
  pending: boolean
  unavailable: boolean
  reload: () => void
  accept: (session: Session) => void
  updateUser: (user: User) => void
  signOut: () => Promise<void>
}
type Preferences = {theme: Theme; setTheme: (theme: Theme) => void; notify: (text: string) => void}

const AuthContext = createContext<Auth | null>(null)
const PreferencesContext = createContext<Preferences | null>(null)

export function useAuth() { return useContext(AuthContext)! }
export function usePreferences() { return useContext(PreferencesContext)! }

export function Providers({children}: {children: ReactNode}) {
  const [user, setUser] = useState<User | null>(null)
  const [pending, setPending] = useState(true)
  const [unavailable, setUnavailable] = useState(false)
  const [revision, setRevision] = useState(0)
  const [toast, setToast] = useState<{text: string} | null>(null)
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem('portal-theme')
    return saved === 'light' || saved === 'dark' ? saved : 'system'
  })

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = () => {
      document.documentElement.dataset.theme = theme === 'system' ? (media.matches ? 'dark' : 'light') : theme
    }
    apply()
    localStorage.setItem('portal-theme', theme)
    media.addEventListener('change', apply)
    return () => media.removeEventListener('change', apply)
  }, [theme])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 4500)
    return () => window.clearTimeout(timer)
  }, [toast])

  function accept(session: Session) {
    setCsrf(session.csrf_token)
    setUser(session.user)
    setUnavailable(false)
  }

  useEffect(() => {
    const controller = new AbortController()
    const interceptor = api.interceptors.response.use(undefined, error => {
      if (statusOf(error) === 401 && !error.config?.url?.startsWith('/auth/')) {
        setUser(null)
        setCsrf()
        setToast({text: 'Your session has ended. Sign in to continue.'})
      }
      return Promise.reject(error)
    })
    api.get<Session>('/auth/me', {signal: controller.signal}).then(({data}) => accept(data))
      .catch(error => {
        if (!controller.signal.aborted && statusOf(error) !== 401) setUnavailable(true)
      }).finally(() => { if (!controller.signal.aborted) setPending(false) })
    return () => {
      controller.abort()
      api.interceptors.response.eject(interceptor)
    }
  }, [revision])

  async function signOut() {
    try {
      await api.post('/auth/logout')
    } catch (error) {
      if (statusOf(error) !== 401) throw error
    }
    setUser(null)
    setCsrf()
    setToast({text: 'You’ve signed out.'})
  }

  return <AuthContext.Provider value={{user, pending, unavailable,
    reload: () => {setPending(true); setUnavailable(false); setRevision(value => value + 1)},
    accept, updateUser: setUser, signOut}}>
    <PreferencesContext.Provider value={{theme, setTheme, notify: text => setToast({text})}}>
      {children}
      <div className="toast-region" aria-live="polite">{toast && <div className="toast">{toast.text}<button
        type="button" onClick={() => setToast(null)} aria-label="Dismiss notification">×</button></div>}</div>
    </PreferencesContext.Provider>
  </AuthContext.Provider>
}
