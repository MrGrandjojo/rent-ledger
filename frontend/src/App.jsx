import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './AuthContext'
import Layout from './components/Layout'
import Login from './pages/Login'
import ChangePassword from './pages/ChangePassword'
import Dashboard from './pages/Dashboard'
import Properties from './pages/Properties'
import Tenants from './pages/Tenants'
import Leases from './pages/Leases'
import LeaseDetail from './pages/LeaseDetail'
import Payments from './pages/Payments'
import Charges from './pages/Charges'
import Documents from './pages/Documents'
import Settings from './pages/Settings'
import Administration from './pages/Administration'
import AuditLogs from './pages/AuditLogs'

function RequireAuth({ children }) {
  const { user } = useAuth()
  if (user === undefined) return <div className="flex items-center justify-center h-screen text-gray-500">Chargement…</div>
  if (!user) return <Navigate to="/login" replace />
  if (user.force_password_change) return <Navigate to="/change-password" replace />
  return children
}

function RequireAdmin({ children }) {
  const { user } = useAuth()
  if (user?.role !== 'admin') return <Navigate to="/dashboard" replace />
  return children
}

function RequireAdminOrSupervisor({ children }) {
  const { user } = useAuth()
  if (user?.role !== 'admin' && user?.role !== 'supervisor') return <Navigate to="/dashboard" replace />
  return children
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/change-password" element={<ChangePassword />} />
      <Route path="/" element={<RequireAuth><Layout /></RequireAuth>}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="properties" element={<Properties />} />
        <Route path="tenants" element={<Tenants />} />
        <Route path="leases" element={<Leases />} />
        <Route path="leases/:id" element={<LeaseDetail />} />
        <Route path="payments" element={<Payments />} />
        <Route path="charges" element={<Charges />} />
        <Route path="documents" element={<Documents />} />
        <Route path="settings" element={<Settings />} />
        <Route path="administration" element={<RequireAdminOrSupervisor><Administration /></RequireAdminOrSupervisor>} />
        <Route path="audit-logs" element={<RequireAdmin><AuditLogs /></RequireAdmin>} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  )
}
