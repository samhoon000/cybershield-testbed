import {AlertCircle, ArrowLeft, Inbox, GraduationCap} from 'lucide-react'
import {Link} from 'react-router-dom'
import {type ReactNode} from 'react'

export function Brand() {
  return <div className="brand"><span className="brand-mark"><GraduationCap size={22} /></span>
    <span><strong>Northfield</strong><small>ACADEMIC PORTAL</small></span></div>
}

export function PageTitle({title, description, action}: {title: string; description?: string; action?: ReactNode}) {
  return <header className="page-title"><div><h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</header>
}

export function BackLink({to, children}: {to: string; children: ReactNode}) {
  return <Link className="back-link" to={to}><ArrowLeft size={16}/>{children}</Link>
}

export function Empty({title, text, action}: {title: string; text?: string; action?: ReactNode}) {
  return <div className="empty"><span><Inbox size={22}/></span><strong>{title}</strong>{text && <p>{text}</p>}{action}</div>
}

export function Failure({message, retry}: {message: string; retry?: () => void}) {
  return <div className="failure" role="alert"><AlertCircle size={18}/><div>{message}</div>
    {retry && <button className="button secondary small" type="button" onClick={retry}>Try again</button>}</div>
}

export function Skeleton() {
  return <div className="skeletons" role="status" aria-label="Loading"><div/><div/><div/></div>
}

export function Paging({page, previous, next}: {page: number; previous: () => void; next?: () => void}) {
  return <div className="paging"><button className="button secondary small" type="button" disabled={page === 1}
    onClick={previous}>Previous</button><span>Page {page}</span><button className="button secondary small"
    type="button" disabled={!next} onClick={next}>Next</button></div>
}

export function ProgressBar({value}: {value: number}) {
  return <div className="progress" role="progressbar" aria-label="Course completion" aria-valuenow={value}
    aria-valuemin={0} aria-valuemax={100}><div style={{width: value + '%'}}/></div>
}

export function initials(name: string) {
  return name.trim().split(/\s+/).slice(0, 2).map(word => word[0]?.toUpperCase()).join('')
}

export function formatDate(value: string, time = false) {
  return new Intl.DateTimeFormat(undefined, time ? {dateStyle: 'medium', timeStyle: 'short'} :
    {day: 'numeric', month: 'short', year: 'numeric'}).format(new Date(value))
}

export function localInputDate(value: string) {
  const date = new Date(value)
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return shifted.toISOString().slice(0, 16)
}
