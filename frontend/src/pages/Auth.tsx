import {BookOpen, CheckCircle2, ClipboardList, LayoutDashboard} from 'lucide-react'
import {useState, type FormEvent} from 'react'
import {Link, Navigate, useLocation, useNavigate} from 'react-router-dom'
import {api, describe, type Session} from '../api'
import {Brand, Failure} from '../components/ui'
import {useAuth, usePreferences} from '../context'

export default function AuthPage({register = false}: {register?: boolean}) {
  const auth = useAuth()
  const {notify} = usePreferences()
  const navigate = useNavigate()
  const location = useLocation()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  if (auth.user) return <Navigate to="/" replace/>

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    const payload = Object.fromEntries(new FormData(event.currentTarget))
    if (register && payload.password !== payload.confirm_password) {
      setError('Passwords must match.')
      return
    }
    setBusy(true)
    try {
      const {data} = await api.post<Session>(register ? '/auth/register' : '/auth/login', payload)
      auth.accept(data)
      if (register) notify('Your student account is ready.')
      const from = (location.state as {from?: string} | null)?.from
      navigate(from?.startsWith('/') && !from.startsWith('//') ? from : '/', {replace: true})
    } catch (problem) {
      setError(describe(problem))
    } finally {
      setBusy(false)
    }
  }

  return <main className="auth-layout">
    <section className="auth-main">
      <Brand/>
      <div className="auth-form">
        <h1>{register ? 'Create your account' : 'Welcome back'}</h1>
        <p>{register ? 'Register as a student to get started.' : 'Sign in to your Northfield academic workspace.'}</p>
        {error && <Failure message={error}/>}
        <form onSubmit={handleSubmit}>
          {register && <label>Full name<input name="full_name" placeholder="Jordan Lee" autoComplete="name" required minLength={2} maxLength={100}/></label>}
          <label>Email address<input name="email" type="email" placeholder="you@example.com" autoComplete="email" required maxLength={254}/></label>
          {register && <label>Student ID<input name="student_id" autoComplete="off" required pattern="[A-Za-z0-9\\-]{3,32}"
            title="3–32 letters, numbers, or hyphens" placeholder="NF-1024"/></label>}
          <label>Password<input name="password" type="password" placeholder={register ? 'At least 12 characters' : 'Enter your password'}
            autoComplete={register ? 'new-password' : 'current-password'} required minLength={register ? 12 : 1} maxLength={128}/></label>
          {register && <label>Confirm password<input name="confirm_password" type="password" autoComplete="new-password" required minLength={12} maxLength={128}/></label>}
          <button type="submit" className="button primary full" disabled={busy}>{busy ? 'Please wait…' : register ? 'Create account' : 'Sign in'}</button>
        </form>
        <p className="auth-switch">{register ? 'Already registered?' : 'New to Northfield?'}{' '}
          <Link to={register ? '/login' : '/register'}>{register ? 'Sign in' : 'Create an account'}</Link>
        </p>
      </div>
      <footer>Northfield Academic Portal</footer>
    </section>
    <aside className="auth-art" aria-label="Portal features">
      <div className="auth-rings" aria-hidden="true"/><div className="auth-art-inner">
        <h2>Your academic day,<br/>in one place.</h2>
        <div className="auth-feature"><BookOpen/>Explore courses and track progress<CheckCircle2/></div>
        <div className="auth-feature"><ClipboardList/>See deadlines and submit work<CheckCircle2/></div>
        <div className="auth-feature"><LayoutDashboard/>Get an overview of your semester<CheckCircle2/></div>
      </div>
    </aside>
  </main>
}
