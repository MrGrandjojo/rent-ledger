import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'
import ProcedureModal from '../components/ProcedureModal'
import {
  fmtCurrency, fmtDate, procedureStatusClass, procedureStatusLabel,
  procedureTypeLabel,
} from '../utils'

const STATUS_FILTERS = [
  { value: '',                label: 'Tous les statuts' },
  { value: 'in_progress',     label: 'En cours' },
  { value: 'paid',            label: 'Payé' },
  { value: 'expired_unpaid',  label: 'Échu impayé' },
  { value: 'cancelled',       label: 'Annulé' },
]

function daysRemainingHint(p) {
  if (p.status === 'paid' || p.status === 'cancelled') return null
  const d = p.days_remaining
  if (d == null) return null
  if (d < 0) return <span className="text-red-600 text-xs">Échu depuis {-d} j</span>
  if (d === 0) return <span className="text-orange-600 text-xs">Échéance aujourd'hui</span>
  if (d <= 7)  return <span className="text-orange-600 text-xs">J-{d}</span>
  return <span className="text-gray-400 text-xs">J-{d}</span>
}

export default function Procedures() {
  const [procedures, setProcedures] = useState([])
  const [leases, setLeases] = useState([])
  const [leaseFilter, setLeaseFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    const params = {}
    if (leaseFilter)  params.lease_id = leaseFilter
    if (statusFilter) params.status   = statusFilter
    const [p, l] = await Promise.all([
      api.get('/procedures', { params }),
      api.get('/leases'),
    ])
    setProcedures(p.data)
    setLeases(l.data)
    setLoading(false)
  }

  useEffect(() => { load() }, [leaseFilter, statusFilter])

  const leaseLabel = (id) => {
    const l = leases.find((x) => x.id === id)
    return l ? `${l.property?.name} — ${l.tenant?.last_name}` : `Bail #${id}`
  }

  const remove = async (proc) => {
    if (!confirm('Supprimer cette procédure ?')) return
    try {
      await api.delete(`/procedures/${proc.id}`)
      load()
    } catch (e) {
      alert(e.response?.data?.detail || 'Erreur')
    }
  }

  if (loading) return <p className="text-gray-400">Chargement…</p>

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-gray-800">Procédures</h1>
        <div className="flex items-center gap-3 flex-wrap">
          <select
            className="form-input w-40"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            {STATUS_FILTERS.map((f) => (
              <option key={f.value} value={f.value}>{f.label}</option>
            ))}
          </select>
          <select
            className="form-input w-64"
            value={leaseFilter}
            onChange={(e) => setLeaseFilter(e.target.value)}
          >
            <option value="">Tous les baux</option>
            {leases.map((l) => (
              <option key={l.id} value={l.id}>
                {l.property?.name} — {l.tenant?.last_name}
              </option>
            ))}
          </select>
          <button className="btn-primary" onClick={() => setShowModal(true)}>
            + Nouveau commandement
          </button>
        </div>
      </div>

      <p className="text-sm text-gray-500">
        Les commandements de payer ouvrent un délai légal de 2 mois pour solder la dette
        locative. Les paiements du bail tombant dans cette fenêtre sont automatiquement
        comptés, on peut aussi rattacher manuellement un paiement.
      </p>

      <div className="card p-0 overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="table-th">Bail</th>
              <th className="table-th">Type</th>
              <th className="table-th">Notification</th>
              <th className="table-th">Échéance</th>
              <th className="table-th">Réclamé</th>
              <th className="table-th">Réglé</th>
              <th className="table-th">Reste</th>
              <th className="table-th">Statut</th>
              <th className="table-th text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {procedures.length === 0 && (
              <tr>
                <td colSpan={9} className="table-td text-center text-gray-400 py-8">
                  Aucune procédure
                </td>
              </tr>
            )}
            {procedures.map((p) => (
              <tr key={p.id} className="hover:bg-gray-50">
                <td className="table-td text-sm">{leaseLabel(p.lease_id)}</td>
                <td className="table-td text-sm">{procedureTypeLabel(p.procedure_type)}</td>
                <td className="table-td text-sm">{fmtDate(p.notification_date)}</td>
                <td className="table-td text-sm">
                  {fmtDate(p.deadline_date)}
                  <div>{daysRemainingHint(p)}</div>
                </td>
                <td className="table-td">{fmtCurrency(p.total_due)}</td>
                <td className="table-td">{fmtCurrency(p.total_paid)}</td>
                <td className="table-td">
                  {Number(p.remaining_due) > 0
                    ? <span className="text-red-600 font-medium">{fmtCurrency(p.remaining_due)}</span>
                    : <span className="text-green-600">0,00 €</span>}
                </td>
                <td className="table-td">
                  <span className={procedureStatusClass(p.status)}>
                    {procedureStatusLabel(p.status)}
                  </span>
                </td>
                <td className="table-td text-right space-x-1 whitespace-nowrap">
                  <Link to={`/procedures/${p.id}`} className="btn-secondary btn-sm">
                    Détail
                  </Link>
                  <button
                    className="btn-secondary btn-sm"
                    title="Modifier"
                    onClick={() => setEditing(p)}
                  >✏️</button>
                  <button
                    className="btn-secondary btn-sm"
                    title="Supprimer"
                    onClick={() => remove(p)}
                  >🗑️</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showModal && (
        <ProcedureModal
          leases={leases}
          onClose={() => setShowModal(false)}
          onSaved={() => { setShowModal(false); load() }}
        />
      )}
      {editing && (
        <ProcedureModal
          procedure={editing}
          leases={leases}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load() }}
        />
      )}
    </div>
  )
}
