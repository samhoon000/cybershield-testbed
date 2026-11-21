import {BookOpen, ChevronDown, Clock3, Plus, Search, Users} from 'lucide-react'
import {useEffect, useState, type FormEvent} from 'react'
import {Link, useNavigate, useParams, useSearchParams} from 'react-router-dom'
import {api, describe} from '../api'
import {CourseCard, CourseSymbol} from '../components/academic'
import {BackLink, Empty, Failure, PageTitle, Paging, ProgressBar, Skeleton} from '../components/ui'
import {useAuth, usePreferences} from '../context'
import {useApi} from '../hooks'
import type {Course, CoursePage} from '../types'

export default function Courses() {
  const {user} = useAuth()
  const [params, setParams] = useSearchParams()
  const enrolled = params.get('view') === 'enrolled' && user?.role === 'student'
  const admin = user?.role === 'admin'
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('')
  const [sort, setSort] = useState('title')
  const [page, setPage] = useState(1)
  const list = useApi<CoursePage>(enrolled ? null : '/courses?' + new URLSearchParams({
    search: query, category, sort, page: String(page),
  }))
  const mine = useApi<Course[]>(enrolled ? '/courses/enrolled' : null)
  const items = enrolled ? mine.data : list.data?.items
  const active = enrolled ? mine : list
  return <>
    <PageTitle title="Courses" description={admin ? 'Manage the course catalog.' : 'Explore the catalog and keep up with your enrolled courses.'}
      action={admin && <Link to="/courses/new" className="button primary"><Plus size={18}/>New course</Link>}/>
    {!admin && <div className="tabs" aria-label="Course view"><button type="button" aria-pressed={!enrolled} onClick={() => setParams({})}>Course directory</button>
      <button type="button" aria-pressed={enrolled} onClick={() => setParams({view: 'enrolled'})}>My courses</button></div>}
    {!enrolled && <form className="panel filters" onSubmit={event => {event.preventDefault(); setPage(1); setQuery(search)}}>
      <label className="search"><span className="sr-only">Search by title</span><Search size={18}/>
        <input value={search} onChange={event => setSearch(event.target.value)}
          placeholder="Search by title" maxLength={120}/></label>
      <button className="button secondary" type="submit">Search</button>
      <label className="select-wrap"><span className="sr-only">Category</span><select value={category} onChange={event => {setCategory(event.target.value); setPage(1)}}>
        <option value="">All categories</option>{[...new Set([...(category ? [category] : []), ...(list.data?.categories ?? [])])]
          .map(name => <option key={name}>{name}</option>)}</select><ChevronDown size={16}/></label>
      <label className="select-wrap"><span className="sr-only">Sort courses</span><select value={sort} onChange={event => {setSort(event.target.value); setPage(1)}}>
        <option value="title">Title A–Z</option><option value="newest">Newest first</option><option value="popular">Most enrolled</option>
      </select><ChevronDown size={16}/></label>
    </form>}
    {active.loading && <Skeleton/>}{active.error && <Failure message={active.error} retry={active.refresh}/>}
    {items && (items.length ? <div className="course-grid">{items.map(course => <CourseCard key={course.id} course={course}/>)}</div> :
      <section className="panel"><Empty title={enrolled ? 'You haven’t enrolled yet' : 'No courses found'}
        text={enrolled ? 'Browse the directory to find a course.' : page > 1 ? 'Return to the previous page to keep browsing.' : 'Try a different search or category.'}
        action={enrolled && <button type="button" className="button secondary" onClick={() => setParams({})}>Browse courses</button>}/></section>)}
    {!enrolled && list.data && (page > 1 || list.data.total > list.data.page_size) && <Paging page={page}
      previous={() => setPage(page - 1)} next={page * list.data.page_size < list.data.total ? () => setPage(page + 1) : undefined}/>}
  </>
}

export function CourseDetail() {
  const {id} = useParams()
  const {user} = useAuth()
  const {notify} = usePreferences()
  const navigate = useNavigate()
  const {data, error, loading, refresh} = useApi<Course>('/courses/' + id)
  const [busy, setBusy] = useState(false)
  const [issue, setIssue] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [progress, setProgress] = useState<number | null>(null)
  const hasEnrollment = data?.progress != null

  useEffect(() => {
    if (hasEnrollment && user?.role === 'student') {
      api.post('/courses/' + id + '/access').catch(() => {})
    }
  }, [id, hasEnrollment, user?.role])

  async function mutate(action: 'enroll' | 'delete' | 'progress') {
    setBusy(true)
    setIssue('')
    try {
      if (action === 'enroll') {
        await api.post('/courses/' + id + '/enroll')
        notify('You’re enrolled in this course.')
      } else if (action === 'delete') {
        await api.delete('/courses/' + id)
        notify('Course deleted.')
        navigate('/courses')
        return
      } else {
        await api.put('/courses/' + id + '/progress', {progress})
        setProgress(null)
        notify('Progress saved.')
      }
      refresh()
    } catch (problem) { setIssue(describe(problem)) } finally { setBusy(false) }
  }

  return <><BackLink to="/courses">Back to courses</BackLink>
    {loading && <Skeleton/>}{error && <Failure message={error} retry={refresh}/>}
    {data && <>
      <PageTitle title={data.title} description={data.category}
        action={user?.role === 'admin' && <Link className="button secondary" to={'/courses/' + id + '/edit'}>Edit course</Link>}/>
      {issue && <Failure message={issue}/>}
      <div className="detail-grid">
        <section className="panel dash-panel">
          <CourseSymbol category={data.category}/><h2>About this course</h2><p className="preserve">{data.description}</p>
          <div className="course-meta"><span><BookOpen size={17}/>{data.instructor}</span><span><Clock3 size={17}/>{data.duration} weeks</span>
            <span><Users size={17}/>{data.enrollment_count} enrolled</span></div>
        </section>
        <section className="panel dash-panel">
          <h2>{hasEnrollment ? 'Your progress' : 'Enrollment'}</h2>
          {hasEnrollment ? <>
            <div className="row between"><span>{data.progress === 100 ? 'Completed' : 'Course completion'}</span><strong>{data.progress}%</strong></div>
            <ProgressBar value={data.progress ?? 0}/>
            <label>Update completion (%)<input type="number" min="0" max="100" value={progress ?? data.progress ?? 0}
              onChange={event => setProgress(event.target.valueAsNumber || 0)}/></label>
            <button type="button" className="button primary" disabled={busy || progress === null || progress < 0 || progress > 100 || !Number.isInteger(progress)}
              onClick={() => mutate('progress')}>Save progress</button>
          </> : <>
            <p>{data.status === 'open' ? 'Open for enrollment.' : 'Enrollment has closed.'}</p>
            {user?.role === 'student' && <button className="button primary" type="button" disabled={busy || data.status !== 'open'}
              onClick={() => mutate('enroll')}>Enroll in course</button>}
          </>}
        </section>
      </div>
      {user?.role === 'admin' && <section className="panel dash-panel"><h2>Delete course</h2>
        <p>Deleting this course also removes its enrollments, assignments, and submissions.</p>
        {confirmDelete ? <div className="row"><button className="button destructive" type="button" disabled={busy} onClick={() => mutate('delete')}>Confirm deletion</button>
          <button className="button secondary" type="button" disabled={busy} onClick={() => setConfirmDelete(false)}>Cancel</button></div> :
          <button className="button destructive" type="button" onClick={() => setConfirmDelete(true)}>Delete course</button>}
      </section>}
    </>}
  </>
}

export function CourseEditor() {
  const {id} = useParams()
  const navigate = useNavigate()
  const {notify} = usePreferences()
  const {data, error, loading, refresh} = useApi<Course>(id ? '/courses/' + id : null)
  const [busy, setBusy] = useState(false)
  const [issue, setIssue] = useState('')
  const back = id ? '/courses/' + id : '/courses'

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const values = Object.fromEntries(new FormData(event.currentTarget))
    const payload = {...values, duration: Number(values.duration)}
    setBusy(true)
    setIssue('')
    try {
      const result = id ? await api.put<Course>('/courses/' + id, payload) : await api.post<Course>('/courses', payload)
      notify(id ? 'Course updated.' : 'Course created.')
      navigate('/courses/' + result.data.id)
    } catch (problem) { setIssue(describe(problem)) } finally { setBusy(false) }
  }

  return <><BackLink to={back}>Back to courses</BackLink><PageTitle title={id ? 'Edit course' : 'New course'}/>
    {loading && <Skeleton/>}{error && <Failure message={error} retry={refresh}/>}
    {(!id || data) && <form className="panel form-panel" onSubmit={save}>
      {issue && <Failure message={issue}/>}
      <label>Course title<input name="title" defaultValue={data?.title} required minLength={2} maxLength={120}/></label>
      <label>Description<textarea name="description" defaultValue={data?.description} required minLength={5} maxLength={8000} rows={5}/></label>
      <div className="form-grid">
        <label>Category<input name="category" defaultValue={data?.category} required minLength={2} maxLength={60}/></label>
        <label>Instructor<input name="instructor" defaultValue={data?.instructor} required minLength={2} maxLength={100}/></label>
        <label>Duration in weeks<input type="number" name="duration" defaultValue={data?.duration ?? 8} required min={1} max={104}/></label>
        <label>Status<span className="select-wrap"><select name="status" defaultValue={data?.status ?? 'open'}>
          <option value="open">Open</option><option value="closed">Closed</option></select><ChevronDown size={16}/></span></label>
      </div>
      <div className="row"><button type="submit" className="button primary" disabled={busy}>{busy ? 'Saving…' : 'Save course'}</button>
        <Link className="button secondary" to={back}>Cancel</Link></div>
    </form>}
  </>
}
