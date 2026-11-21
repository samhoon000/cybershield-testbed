export type Role = 'student' | 'admin'

export interface User {
  id: number
  full_name: string
  email: string
  student_id: string
  role: Role
  department: string
  academic_year: number | null
  created_at: string
}

export interface Course {
  id: number
  title: string
  description: string
  category: string
  instructor: string
  duration: number
  status: 'open' | 'closed'
  enrollment_count: number
  progress: number | null
  completed_at: string | null
}

export interface Assignment {
  id: number
  course_id: number
  course_title: string
  title: string
  description: string
  deadline: string
  submission_count: number
  overdue: boolean
}

export interface Submission {
  id: number
  content: string
  submitted_at: string
  status: string
  student_id?: string
  student_name?: string
}

export interface Activity {
  id: number
  user_id: number | null
  event_type: string
  resource_type: string | null
  resource_id: number | null
  outcome: string
  request_id: string
  created_at: string
}

export interface StudentDashboard {
  role: 'student'
  enrolled: number
  completed: number
  pending: number
  progress: number
  recent_courses: Course[]
  upcoming: Assignment[]
  submission_stats: {name: string; value: number}[]
  activity: Activity[]
}

export interface AdminDashboard {
  role: 'admin'
  students: number
  courses: number
  assignments: number
  submissions: number
  activity: Activity[]
}

export type DashboardData = StudentDashboard | AdminDashboard
export type Profile = User & {enrolled_courses: Course[]}
export type CoursePage = {items: Course[]; total: number; page: number; page_size: number; categories: string[]}
