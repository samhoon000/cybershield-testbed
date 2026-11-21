import {CalendarDays, ChevronDown, ClipboardList, Plus} from 'lucide-react'
import {useState, type FormEvent} from 'react'
import {Link, useNavigate, useParams} from 'react-router-dom'
import {api, describe} from '../api'
import {AssignmentStatus} from '../components/academic'
import {BackLink, Empty, Failure, formatDate, localInputDate, PageTitle, Paging, Skeleton} from '../components/ui'
import {useAuth, usePreferences} from '../context'
import {useApi} from '../hooks'
import type {Assignment, CoursePage, Submission} from '../types'

export default function Assignments() {
  const {user} = useAuth()
  const admin = user?.role === 'admin'
  const {data, error, loading, refresh} = useApi<Assignment[]>('/assignments')
  const [filter, setFilter] = useState('all')
  const items = data?.filter(assignment => filter === 'all' || ({
    submitted: assignment.submission_count > 0,
    pending: !assignment.overdue && !assignment.submission_count,
    overdue: assignment.overdue && !assignment.submission_count,
  }[filter]))
  return <>
    <PageTitle title="Assignments" description={admin ? 'Manage coursework, deadlines, and submissions.' : 'Keep track of due dates and submit your coursework.'}
      action={admin && <Link className="button primary" to="/assignments/new"><Plus size={18}/>New assignment</Link>}/>
    {!admin && <div className="tabs" aria-label="Assignment status">{['all', 'pending', 'submitted', 'overdue'].map(value =>
      <button key={value} type="button" aria-pressed={value === filter} onClick={() => setFilter(value)}>
        {value.charAt(0).toUpperCase() + value.slice(1)}</button>)}</div>}
    {loading && <Skeleton/>}{error && <Failure message={error} retry={refresh}/>}
    {items && <section className="panel dash-panel">
      {items.length ? <div className="item-list">{items.map(item =>
        <Link className="item-line assignment-row" key={item.id} to={'/assignments/' + item.id}>
          <span className="symbol lavender"><ClipboardList size={21}/></span>
          <div><strong>{item.title}</strong><small>{item.course_title} · Due {formatDate(item.deadline, true)}</small></div>
          {admin ? <span className="pill">{item.submission_count} {item.submission_count === 1 ? 'submission' : 'submissions'}</span> :
            <AssignmentStatus assignment={item}/>}
        </Link>)}</div> : <Empty title="No assignments found"
        text={admin ? 'Create an assignment to make it available to enrolled students.' : 'Assignments for your enrolled courses appear here.'}/>}
    </section>}
  </>
}

export function AssignmentDetail() {
  const {id} = useParams()
  const {user} = useAuth()
  const admin = user?.role === 'admin'
  const {notify} = usePreferences()
  const [page, setPage] = useState(1)
  const [submissionText, setSubmissionText] = useState('')
  const [busy, setBusy] = useState(false)
  const [issue, setIssue] = useState('')
  const path = '/assignments/' + id
  const assignment = useApi<Assignment>(path)
  const history = useApi<Submission[]>(assignment.data ? path + '/submissions?offset=' + (page - 1) * 25 : null)
  const data = assignment.data

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIssue('')
    setBusy(true)
    try {
      await api.post(path + '/submit', {content: submissionText})
      setSubmissionText('')
      setPage(1)
      assignment.refresh()
      history.refresh()
      notify('Assignment submitted.')
    } catch (problem) { setIssue(describe(problem)) } finally { setBusy(false) }
  }

  return <><BackLink to="/assignments">Back to assignments</BackLink>
    {assignment.loading && <Skeleton/>}{assignment.error && <Failure message={assignment.error} retry={assignment.refresh}/>}
    {data && <>
      <PageTitle title={data.title} description={data.course_title} action={admin ?
        <Link className="button secondary" to={path + '/edit'}>Edit assignment</Link> : <AssignmentStatus assignment={data}/>}/>
      <section className="panel dash-panel"><h2>Instructions</h2><p className="preserve">{data.description}</p>
        <p className="row"><CalendarDays size={18}/>Due {formatDate(data.deadline, true)}</p></section>
      {!admin && !data.overdue && <form className="panel form-panel" onSubmit={submit}>
        <h2>{data.submission_count ? 'Submit a new version' : 'Submit your work'}</h2>
        {issue && <Failure message={issue}/>}
        <label>Assignment response<textarea rows={8} value={submissionText} onChange={event => setSubmissionText(event.target.value)}
          required maxLength={10000}/><small>{submissionText.length.toLocaleString()} / 10,000 characters</small></label>
        <button className="button primary" type="submit" disabled={busy || !submissionText.trim()}>{busy ? 'Submitting…' : 'Submit assignment'}</button>
      </form>}
      {!admin && data.overdue && <p className="notice">Submissions closed on {formatDate(data.deadline, true)}.</p>}
      <section className="panel dash-panel"><h2>{admin ? 'Student submissions' : 'Submission history'}</h2>
        {history.loading && <Skeleton/>}{history.error && <Failure message={history.error} retry={history.refresh}/>}
        {history.data && (history.data.length ? <div className="history-list">{history.data.map(item =>
          <details key={item.id}><summary><span>{admin ? item.student_name + ' · ' + item.student_id : 'Submitted'}<small>
            {formatDate(item.submitted_at, true)}</small></span></summary><p className="preserve">{item.content}</p></details>)}</div> :
          <Empty title="No submissions yet"/>)}
        {data.submission_count > 25 && <Paging page={page} previous={() => setPage(page - 1)}
          next={page * 25 < data.submission_count ? () => setPage(page + 1) : undefined}/>}
      </section>
    </>}
  </>
}

export function AssignmentEditor() {
  const {id} = useParams()
  const navigate = useNavigate()
  const {notify} = usePreferences()
  const assignment = useApi<Assignment>(id ? '/assignments/' + id : null)
  const [page, setPage] = useState(1)
  const [query, setQuery] = useState('')
  const [selection, setSelection] = useState<{id: number; title: string}>()
  const courses = useApi<CoursePage>(id ? null : '/courses?' + new URLSearchParams({page: String(page), search: query}))
  const [busy, setBusy] = useState(false)
  const [issue, setIssue] = useState('')
  const back = id ? '/assignments/' + id : '/assignments'
  const data = assignment.data
  const choices = courses.data?.items ?? []

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const values = new FormData(event.currentTarget)
    setIssue('')
    const input = String(values.get('deadline'))
    const deadline = new Date(input)
    const unchanged = Boolean(data && input === localInputDate(data.deadline))
    if (!Number.isFinite(deadline.getTime()) || (!unchanged && deadline <= new Date())) {
      setIssue('Choose a future deadline.')
      return
    }
    const payload = {course_id: data?.course_id ?? selection?.id, title: values.get('title'),
      description: values.get('description'), deadline: unchanged ? data!.deadline : deadline.toISOString()}
    setBusy(true)
    try {
      const result = id ? await api.put<Assignment>(back, payload) : await api.post<Assignment>('/assignments', payload)
      notify(id ? 'Assignment updated.' : 'Assignment created.')
      navigate('/assignments/' + result.data.id)
    } catch (problem) { setIssue(describe(problem)) } finally { setBusy(false) }
  }

  return <><BackLink to={back}>Back to assignments</BackLink><PageTitle title={id ? 'Edit assignment' : 'New assignment'}/>
    {assignment.loading && <Skeleton/>}{assignment.error && <Failure message={assignment.error} retry={assignment.refresh}/>}
    {(!id || data) && <form className="panel form-panel" onSubmit={save}>
      {issue && <Failure message={issue}/>}
      {id ? <label>Course<input value={data?.course_title} readOnly/></label> : <fieldset>
        <legend>Course</legend>
        <label>Find a course<input value={query} maxLength={120} placeholder="Search course title"
          onChange={event => {setQuery(event.target.value); setPage(1)}}/></label>
        {courses.error && <Failure message={courses.error} retry={courses.refresh}/>}
        <label>Choose course<span className="select-wrap"><select required value={selection?.id ?? ''}
          onChange={event => setSelection(choices.find(course => String(course.id) === event.target.value))}>
          <option value="">{courses.loading ? 'Loading courses…' : 'Select a course'}</option>
          {selection && !choices.some(course => course.id === selection.id) && <option value={selection.id}>{selection.title}</option>}
          {choices.map(course => <option key={course.id} value={course.id}>{course.title}</option>)}
        </select><ChevronDown size={16}/></span></label>
        {courses.data && (page > 1 || courses.data.total > courses.data.page_size) && <Paging page={page}
          previous={() => setPage(page - 1)} next={page * courses.data.page_size < courses.data.total ? () => setPage(page + 1) : undefined}/>}
      </fieldset>}
      <label>Title<input name="title" defaultValue={data?.title} required minLength={2} maxLength={120}/></label>
      <label>Instructions<textarea name="description" defaultValue={data?.description} required rows={6} minLength={5} maxLength={8000}/></label>
      <label>Deadline (local time)<input type="datetime-local" name="deadline" required
        defaultValue={data?.deadline ? localInputDate(data.deadline) : undefined}/></label>
      <div className="row"><button className="button primary" type="submit" disabled={busy || (!id && !selection)}>
        {busy ? 'Saving…' : 'Save assignment'}</button><Link className="button secondary" to={back}>Cancel</Link></div>
    </form>}
  </>
}
