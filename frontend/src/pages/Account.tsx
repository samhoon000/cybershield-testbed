import {ChevronDown, Laptop, Moon, Sun} from 'lucide-react'
import {useState, type FormEvent} from 'react'
import {api, describe} from '../api'
import {CourseCard, eventLabels} from '../components/academic'
import {Empty, Failure, formatDate, initials, PageTitle, Paging, Skeleton} from '../components/ui'
import {useAuth, usePreferences} from '../context'
import {useApi} from '../hooks'
import type {Activity, Profile as ProfileData, User} from '../types'

export function Profile() {
  const {updateUser} = useAuth()
  const {notify} = usePreferences()
  const {data, loading, error, refresh} = useApi<ProfileData>('/students/me')
  const [busy, setBusy] = useState(false)
  const [issue, setIssue] = useState('')

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const values = new FormData(event.currentTarget)
    const year = values.get('academic_year')
    setBusy(true)
    setIssue('')
    try {
      const result = await api.put<ProfileData>('/students/me', {
        full_name: values.get('full_name'), department: values.get('department'), academic_year: year ? Number(year) : null,
      })
      updateUser(result.data)
      refresh()
      notify('Profile updated.')
    } catch (problem) { setIssue(describe(problem)) } finally { setBusy(false) }
  }

  return <>
    <PageTitle title={data?.role === 'admin' ? 'Profile' : 'Student profile'} description="Review and update your account details."/>
    {loading && <Skeleton/>}{error && <Failure message={error} retry={refresh}/>}
    {data && <>
      <section className="panel profile-banner"><span className="avatar">{initials(data.full_name)}</span><div>
        <h2>{data.full_name}</h2><p>{data.department || (data.role === 'admin' ? 'Administrator' : 'Student account')}</p></div></section>
      <form className="panel form-panel" onSubmit={save}><h2>Personal details</h2>
        {issue && <Failure message={issue}/>}
        <div className="form-grid">
          <label>Full name<input name="full_name" defaultValue={data.full_name} required minLength={2} maxLength={100}/></label>
          <label>Email address<input value={data.email} readOnly/></label>
          <label>{data.role === 'admin' ? 'Account ID' : 'Student ID'}<input value={data.student_id} readOnly/></label>
          <label>Department<input name="department" defaultValue={data.department} maxLength={100}/></label>
          <label>Academic year<input name="academic_year" type="number" min={1} max={8} defaultValue={data.academic_year ?? ''}/></label>
          <label>Account created<input value={formatDate(data.created_at)} readOnly/></label>
        </div>
        <button className="button primary" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save changes'}</button>
      </form>
      {data.role === 'student' && <section className="profile-courses"><h2>Enrolled courses</h2>
        {data.enrolled_courses.length ? <div className="course-grid">{data.enrolled_courses.map(course =>
          <CourseCard key={course.id} course={course}/>)}</div> : <div className="panel"><Empty title="No courses yet"/></div>}</section>}
    </>}
  </>
}

export function ActivityHistory() {
  const {user} = useAuth()
  const admin = user?.role === 'admin'
  const [filter, setFilter] = useState('')
  const [page, setPage] = useState(1)
  const {data, loading, error, refresh} = useApi<Activity[]>('/activity?' + new URLSearchParams({
    event_type: filter, offset: String((page - 1) * 25), limit: '26',
  }))
  return <>
    <PageTitle title="Activity history" description={admin ? 'Review application activity and its outcomes.' : 'Review recent activity on your account.'}/>
    <div className="panel filters"><label className="select-wrap"><span className="sr-only">Activity type</span>
      <select value={filter} onChange={event => {setFilter(event.target.value); setPage(1)}}>
        <option value="">All event types</option>{Object.entries(eventLabels).filter(([key]) =>
          admin || (key !== 'login_failed' && key !== 'authentication_rate_limited' && key !== 'authentication_failed'))
          .map(([key, name]) => <option value={key} key={key}>{name}</option>)}</select><ChevronDown size={16}/></label></div>
    {loading && <Skeleton/>}{error && <Failure message={error} retry={refresh}/>}
    {data && (data.length ? <section className="panel table-scroll"><table><thead><tr><th>Event</th>
      <th>Time</th><th>Outcome</th><th>Resource</th>{admin && <><th>User</th><th>Request ID</th></>}</tr></thead>
      <tbody>{data.slice(0, 25).map(event => <tr key={event.id}><td><strong>{eventLabels[event.event_type] || event.event_type}</strong></td>
        <td>{formatDate(event.created_at, true)}</td><td><span className={'pill ' + (event.outcome === 'success' ? 'success' : 'danger')}>{event.outcome}</span></td>
        <td>{event.resource_type ? event.resource_type + ' #' + event.resource_id : '—'}</td>
        {admin && <><td>{event.user_id ?? '—'}</td><td><code>{event.request_id}</code></td></>}</tr>)}</tbody></table></section> :
      <section className="panel"><Empty title="No matching activity"/></section>)}
    {data && (page > 1 || data.length > 25) && <Paging page={page} previous={() => setPage(page - 1)}
      next={data.length > 25 ? () => setPage(page + 1) : undefined}/>}
  </>
}

export function Students() {
  const [page, setPage] = useState(1)
  const {data, loading, error, refresh} = useApi<User[]>('/students?limit=26&offset=' + (page - 1) * 25)
  return <>
    <PageTitle title="Students" description="View registered students and their academic details."/>
    {loading && <Skeleton/>}{error && <Failure message={error} retry={refresh}/>}
    {data && (data.length ? <section className="panel table-scroll"><table><thead><tr><th>Name</th><th>Student ID</th><th>Email</th>
      <th>Department</th><th>Year</th></tr></thead><tbody>{data.slice(0, 25).map(student => <tr key={student.id}><td><strong>{student.full_name}</strong></td>
        <td>{student.student_id}</td><td>{student.email}</td><td>{student.department || '—'}</td><td>{student.academic_year ?? '—'}</td>
      </tr>)}</tbody></table></section> : <section className="panel"><Empty title="No students found"/></section>)}
    {data && (page > 1 || data.length > 25) && <Paging page={page} previous={() => setPage(page - 1)}
      next={data.length > 25 ? () => setPage(page + 1) : undefined}/>}
  </>
}

export function Settings() {
  const {theme, setTheme} = usePreferences()
  return <>
    <PageTitle title="Settings" description="Set your display preferences for this browser."/>
    <section className="panel dash-panel"><h2>Appearance</h2><p>Choose a color theme for the portal.</p>
      <div className="theme-grid" aria-label="Color theme">{([{label: 'Light', value: 'light', Icon: Sun},
        {label: 'Dark', value: 'dark', Icon: Moon}, {label: 'System', value: 'system', Icon: Laptop}] as const)
        .map(({label, value, Icon}) => <button className="theme-choice" type="button" key={value} aria-pressed={theme === value}
          onClick={() => setTheme(value)}><Icon size={22}/>{label}</button>)}</div>
    </section>
  </>
}
