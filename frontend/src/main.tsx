import {lazy, Suspense, type ReactNode} from 'react'
import {createRoot} from 'react-dom/client'
import {BrowserRouter, Link, Navigate, Outlet, Route, Routes, useLocation} from 'react-router-dom'
import {Brand, Empty, Failure, Skeleton} from './components/ui'
import IncidentScreen from './components/IncidentScreen'
import {Providers, useAuth} from './context'
import Shell from './layouts/Shell'
import AuthPage from './pages/Auth'
import Courses, {CourseDetail, CourseEditor} from './pages/Courses'
import Assignments, {AssignmentDetail, AssignmentEditor} from './pages/Assignments'
import {ActivityHistory, Profile, Settings, Students} from './pages/Account'
import './styles.css'

const Dashboard = lazy(() => import('./pages/Dashboard'))

function Protected() {
  const {user} = useAuth()
  const location = useLocation()
  return user ? <Shell/> : <Navigate to="/login" state={{from: location.pathname + location.search}} replace/>
}

function Admin() {
  const {user} = useAuth()
  return user?.role === 'admin' ? <Outlet/> : <Navigate to="/" replace/>
}

function AccountCheck({children}: {children: ReactNode}) {
  const {pending, unavailable, reload} = useAuth()
  if (pending || unavailable) return <main className="boot"><Brand/>{pending ? <Skeleton/> :
    <Failure message="The portal couldn’t connect to the API." retry={reload}/>}</main>
  return children
}

createRoot(document.getElementById('root')!).render(<BrowserRouter><Providers>
  <IncidentScreen />
  <AccountCheck>
  <Suspense fallback={<main className="boot"><Skeleton/></main>}><Routes>
    <Route path="/login" element={<AuthPage key="login"/>}/>
    <Route path="/register" element={<AuthPage key="register" register/>}/>
    <Route element={<Protected/>}>
      <Route index element={<Dashboard/>}/>
      <Route path="/courses" element={<Courses/>}/>
      <Route path="/courses/:id" element={<CourseDetail/>}/>
      <Route path="/assignments" element={<Assignments/>}/>
      <Route path="/assignments/:id" element={<AssignmentDetail/>}/>
      <Route path="/profile" element={<Profile/>}/>
      <Route path="/activity" element={<ActivityHistory/>}/>
      <Route path="/settings" element={<Settings/>}/>
      <Route element={<Admin/>}>
        <Route path="/students" element={<Students/>}/>
        <Route path="/courses/new" element={<CourseEditor key="new-course"/>}/>
        <Route path="/courses/:id/edit" element={<CourseEditor key="edit-course"/>}/>
        <Route path="/assignments/new" element={<AssignmentEditor key="new-assignment"/>}/>
        <Route path="/assignments/:id/edit" element={<AssignmentEditor key="edit-assignment"/>}/>
      </Route>
      <Route path="*" element={<section className="panel"><Empty title="Page not found"
        action={<Link to="/" className="button primary">Back to dashboard</Link>}/></section>}/>
    </Route>
  </Routes></Suspense>
</AccountCheck></Providers></BrowserRouter>)
