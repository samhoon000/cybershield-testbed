import {Activity as ActivityIcon, BookOpen, CalendarDays, Clock3, Code2, FlaskConical, Palette, Users} from 'lucide-react'
import {Link} from 'react-router-dom'
import type {Activity, Assignment, Course} from '../types'
import {Empty, formatDate, ProgressBar} from './ui'

export function CourseSymbol({category}: {category: string}) {
  const name = category.toLowerCase()
  const [Icon, shade] = name.includes('design') ? [Palette, 'lavender'] :
    name.includes('comput') ? [Code2, 'blue'] : name.includes('science') ? [FlaskConical, 'green'] : [BookOpen, 'amber']
  return <span className={'symbol ' + shade}><Icon size={21}/></span>
}

export function CourseCard({course}: {course: Course}) {
  return <Link className="panel course-card" to={'/courses/' + course.id}>
    <div className="row between"><CourseSymbol category={course.category}/>
      <span className={'pill ' + (course.status === 'open' ? 'success' : '')}>{course.status === 'open' ? 'Open' : 'Closed'}</span></div>
    <div><span className="course-category">{course.category}</span><h2>{course.title}</h2><p className="line-clamp-2">{course.description}</p></div>
    <div className="course-meta"><span><Clock3 size={15}/>{course.duration} weeks</span><span><Users size={15}/>{course.enrollment_count} enrolled</span></div>
    {course.progress !== null && <div><div className="row between muted"><span>Course progress</span><strong>{course.progress}%</strong></div>
      <ProgressBar value={course.progress}/></div>}
  </Link>
}

export function AssignmentStatus({assignment}: {assignment: Assignment}) {
  return assignment.submission_count > 0 ? <span className="pill success">Submitted</span> :
    <span className={'pill ' + (assignment.overdue ? 'danger' : 'warn')}>{assignment.overdue ? 'Overdue' : 'Pending'}</span>
}

export function Upcoming({items}: {items: Assignment[]}) {
  if (!items.length) return <Empty title="You’re all caught up" text="Upcoming assignment deadlines will appear here."/>
  return <div className="item-list">{items.map(item => <Link to={'/assignments/' + item.id} className="item-line" key={item.id}>
    <span className="symbol lavender"><CalendarDays size={19}/></span>
    <div><strong>{item.title}</strong><small>{item.course_title}</small></div><span className="item-end">{formatDate(item.deadline)}</span>
  </Link>)}</div>
}

export const eventLabels: Record<string, string> = {
  account_registered: 'Account created', login_succeeded: 'Signed in', login_failed: 'Unsuccessful sign-in',
  logout: 'Signed out', course_enrolled: 'Course enrollment', profile_updated: 'Profile updated',
  assignment_submitted: 'Assignment submitted', authentication_failed: 'Authentication denied',
  authorization_failed: 'Access denied', authentication_rate_limited: 'Sign-in rate limit',
}

export function RecentActivity({items}: {items: Activity[]}) {
  if (!items.length) return <Empty title="No activity yet" text="Your recent portal activity will appear here."/>
  return <div className="item-list">{items.map(item => <div className="item-line" key={item.id}>
    <span className="symbol blue"><ActivityIcon size={19}/></span>
    <div><strong>{eventLabels[item.event_type] ?? item.event_type}</strong><small>{item.resource_type ?
      item.resource_type + ' #' + item.resource_id : 'Account activity'}</small></div>
    <span className="item-end">{formatDate(item.created_at)}</span>
  </div>)}</div>
}
