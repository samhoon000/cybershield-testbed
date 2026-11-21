import {BarChart3, BookOpen, CalendarDays, CheckCircle2, ClipboardList, Clock3, GraduationCap, Users, type LucideIcon} from 'lucide-react'
import {Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis} from 'recharts'
import {Link} from 'react-router-dom'
import {CourseSymbol, RecentActivity, Upcoming} from '../components/academic'
import {Empty, Failure, PageTitle, ProgressBar, Skeleton} from '../components/ui'
import {useAuth} from '../context'
import {useApi} from '../hooks'
import type {DashboardData, StudentDashboard} from '../types'

type Metric = {label: string; value: number | string; Icon: LucideIcon; shade: string}

function Metrics({items}: {items: Metric[]}) {
  return <div className="metric-grid">{items.map(({label, value, Icon, shade}) =>
    <article className="panel metric" key={label}><span className={'symbol ' + shade}><Icon size={21}/></span>
      <p>{label}</p><strong>{value}</strong></article>)}</div>
}

const chartColors = ['#5264df', '#21a387', '#e3a043']

function StudentCharts({data}: {data: StudentDashboard}) {
  const courseData = data.recent_courses.map(course => ({name: course.title, Progress: course.progress ?? 0}))
  const hasSubmissions = data.submission_stats.some(item => item.value > 0)
  return <div className="dashboard-grid">
    <section className="panel dash-panel">
      <h2>Course progress</h2><p>Completion across your recently accessed courses.</p>
      {courseData.length ? <div className="chart-box" role="img" aria-label={courseData.map(course =>
        course.name + ' ' + course.Progress + '%').join(', ')}>
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <BarChart data={courseData} layout="vertical" margin={{top: 12, right: 18, bottom: 0, left: 0}}>
            <CartesianGrid horizontal={false} stroke="var(--border)" strokeDasharray="4 4"/>
            <XAxis type="number" domain={[0, 100]} tickFormatter={value => value + '%'} stroke="var(--muted)" fontSize={12}/>
            <YAxis width={106} type="category" dataKey="name" tickFormatter={value => value.length > 14 ? value.slice(0, 13) + '…' : value}
              stroke="var(--muted)" tickLine={false} axisLine={false} fontSize={12}/>
            <Tooltip contentStyle={{background: 'var(--panel)', borderColor: 'var(--border)', color: 'var(--text)'}}/>
            <Bar dataKey="Progress" fill="#6373eb" barSize={15} radius={[0, 5, 5, 0]}/>
          </BarChart>
        </ResponsiveContainer>
      </div> : <Empty title="No courses to chart" text="Enroll in a course to start tracking your progress."/>}
    </section>
    <section className="panel dash-panel">
      <h2>Assignment status</h2><p>Your submissions across enrolled courses.</p>
      {hasSubmissions ? <div className="donut-and-legend">
        <div className="donut" aria-hidden="true"><ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <PieChart><Pie data={data.submission_stats} dataKey="value" innerRadius="60%" outerRadius="89%" stroke="none" paddingAngle={3}>
            {data.submission_stats.map(item => <Cell key={item.name} fill={chartColors[data.submission_stats.indexOf(item)]}/>)}
          </Pie></PieChart>
        </ResponsiveContainer></div>
        <ul className="legend">{data.submission_stats.map(({name, value}, index) =>
          <li key={name}><i style={{background: chartColors[index]}}/><span>{name}</span><strong>{value}</strong></li>)}</ul>
      </div> : <Empty title="No assignments yet" text="Status totals will appear when you have assignments."/>}
    </section>
  </div>
}

export default function Dashboard() {
  const {user} = useAuth()
  const {data, error, loading, refresh} = useApi<DashboardData>('/dashboard/stats')
  const date = new Intl.DateTimeFormat(undefined, {weekday: 'long', month: 'long', day: 'numeric'}).format(new Date())
  const admin = data?.role === 'admin'
  return <>
    <PageTitle title="Dashboard" description="Your academic workspace at a glance." action={<span className="date-label"><CalendarDays size={17}/>{date}</span>}/>
    <section className="dashboard-hero"><div className="hero-decoration" aria-hidden="true"><i/><i/><i/></div>
      <div><p><GraduationCap size={18}/>{user?.role === 'admin' ? 'ADMIN WORKSPACE' : 'STUDENT WORKSPACE'}</p>
        <h2>Welcome back, {user?.full_name.trim().split(/\s+/)[0]}.</h2>
        <p className="hero-copy">{user?.role === 'admin' ? 'Manage your courses, assignments, and student records.' :
          'Pick up where you left off and stay on top of upcoming deadlines.'}</p>
        <div className="row flex-wrap"><Link className="button hero-primary" to="/courses">Browse courses</Link>
          <Link className="button hero-secondary" to="/assignments">View assignments</Link></div>
      </div>
    </section>
    {loading && <Skeleton/>}{error && <Failure message={error} retry={refresh}/>}
    {data && (admin ? <Metrics items={[
      {label: 'Students', value: data.students, Icon: Users, shade: 'blue'},
      {label: 'Courses', value: data.courses, Icon: BookOpen, shade: 'green'},
      {label: 'Assignments', value: data.assignments, Icon: ClipboardList, shade: 'amber'},
      {label: 'Submissions', value: data.submissions, Icon: CheckCircle2, shade: 'lavender'},
    ]}/> : <>
      <Metrics items={[
        {label: 'Enrolled courses', value: data.enrolled, Icon: BookOpen, shade: 'blue'},
        {label: 'Completed courses', value: data.completed, Icon: CheckCircle2, shade: 'green'},
        {label: 'Pending assignments', value: data.pending, Icon: Clock3, shade: 'amber'},
        {label: 'Overall progress', value: data.progress + '%', Icon: BarChart3, shade: 'lavender'},
      ]}/>
      <StudentCharts data={data}/>
      <div className="dashboard-grid">
        <section className="panel dash-panel"><div className="row between"><h2>Recently accessed</h2><Link to="/courses?view=enrolled">My courses</Link></div>
          {data.recent_courses.length ? <div className="item-list">{data.recent_courses.map(course =>
            <Link to={'/courses/' + course.id} className="item-line" key={course.id}><CourseSymbol category={course.category}/>
              <div><strong>{course.title}</strong><small>{course.category}</small></div>
              <div className="item-progress"><strong>{course.progress}%</strong><ProgressBar value={course.progress ?? 0}/></div></Link>)}</div> :
            <Empty title="No courses yet" text="Courses you enroll in will appear here."/>}
        </section>
        <section className="panel dash-panel"><div className="row between"><h2>Upcoming deadlines</h2><Link to="/assignments">View all</Link></div>
          <Upcoming items={data.upcoming}/></section>
      </div>
    </>)}
    {data && <section className="panel dash-panel"><div className="row between"><h2>Recent activity</h2><Link to="/activity">View history</Link></div>
      <RecentActivity items={data.activity}/></section>}
  </>
}
