import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'

const NAV = [
  { to: '/dashboard',     label: 'Tableau de bord', icon: '🏠' },
  { to: '/properties',    label: 'Biens',           icon: '🏢' },
  { to: '/tenants',       label: 'Locataires',      icon: '👤' },
  { to: '/leases',        label: 'Baux',            icon: '📄' },
  { to: '/payments',      label: 'Paiements',       icon: '💶' },
  { to: '/charges',       label: 'Charges',         icon: '📊' },
  { to: '/documents',     label: 'Documents',       icon: '📁' },
  { to: '/settings',      label: 'Paramètres',      icon: '⚙️' },
  { to: '/administration', label: 'Administration', icon: '🛡️', requireRole: ['admin', 'supervisor'] },
  { to: '/audit-logs',    label: 'Journaux',        icon: '📜', requireRole: ['admin'] },
]

function roleLabel(role) {
  if (role === 'admin') return 'Administrateur'
  if (role === 'supervisor') return 'Superviseur'
  return 'Bailleur'
}

function deriveDisplayName(user) {
  const landlord = user?.profile?.landlord_name?.trim()
  if (landlord) return landlord
  return user?.username || ''
}

function deriveInitials(user) {
  const landlord = user?.profile?.landlord_name?.trim()
  if (landlord) {
    const parts = landlord.split(/\s+/).filter(Boolean)
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  }
  const u = user?.username || ''
  return u.slice(0, 2).toUpperCase()
}

export default function Sidebar({ onClose }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const role = user?.role
  const items = NAV.filter((n) => !n.requireRole || n.requireRole.includes(role))

  const goToSettings = () => {
    if (onClose) onClose()
    navigate('/settings')
  }

  return (
    <div className="flex flex-col h-full bg-slate-900 text-white w-64">
      <div className="px-6 py-5 border-b border-slate-700">
        <h1 className="text-lg font-bold tracking-tight">Gestion Locative</h1>
        <p className="text-xs text-slate-400 mt-0.5">{roleLabel(role)}</p>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {items.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onClose}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-300 hover:bg-slate-800 hover:text-white'
              }`
            }
          >
            <span className="text-base">{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="px-3 py-4 border-t border-slate-700 space-y-2">
        {user && (
          <button
            onClick={goToSettings}
            title="Aller dans Paramètres"
            className="flex items-center gap-3 w-full px-2 py-2 rounded-lg text-sm font-medium text-slate-200 hover:bg-slate-800 transition-colors text-left"
          >
            <span className="flex items-center justify-center w-8 h-8 rounded-full bg-blue-600 text-white text-xs font-semibold flex-shrink-0">
              {deriveInitials(user)}
            </span>
            <span className="flex flex-col min-w-0">
              <span className="truncate">{deriveDisplayName(user)}</span>
              <span className="text-xs text-slate-400 truncate">{roleLabel(role)}</span>
            </span>
          </button>
        )}
        <button
          onClick={logout}
          className="flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
        >
          <span>🚪</span> Déconnexion
        </button>
      </div>
    </div>
  )
}
