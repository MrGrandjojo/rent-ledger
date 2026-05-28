import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import api from '../api'
import ProcedureModal from '../components/ProcedureModal'
import StatusBadge from '../components/StatusBadge'
import {
  fmtCurrency, fmtDate, MONTHS_FR, procedureStatusClass,
  procedureStatusLabel, procedureTypeLabel,
} from '../utils'

function Field({ label, children }) {
  return (
    <div>
      <div className="text-xs uppercase text-gray-500">{label}</div>
      <div className="text-sm text-gray-800 mt-0.5">{children}</div>
    </div>
  )
}

export default function ProcedureDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [procedure, setProcedure] = useState(null)
  const [lease, setLease] = useState(null)
  const [allPayments, setAllPayments] = useState([])
  const [showEdit, setShowEdit] = useState(false)
  const [showAttach, setShowAttach] = useState(false)
  const [pickPaymentId, setPickPaymentId] = useState('')
  const [loading, setLoading] = useState(true)

  const load = async () => {
    const r = await api.get(`/procedures/${id}`)
    setProcedure(r.data)
    const lr = await api.get(`/leases/${r.data.lease_id}`)
    setLease(lr.data)
    const pr = await api.get('/payments', { params: { lease_id: r.data.lease_id, page_size: 500 } })
    setAllPayments(pr.data.items)
    setLoading(false)
  }

  useEffect(() => { load() }, [id])

  if (loading || !procedure) return <p className="text-gray-400">Chargement…</p>

  const attached = procedure.attached_payments || []
  const attachedIds = new Set(attached.map((a) => a.payment.id))
  // Candidates for manual attach: payments of the lease NOT already attached.
  const candidates = allPayments.filter((p) => !attachedIds.has(p.id))

  const attachPayment = async () => {
    if (!pickPaymentId) return
    try {
      await api.post(`/procedures/${procedure.id}/payments`, {
        payment_id: Number(pickPaymentId),
      })
      toast.success('Paiement rattaché')
      setShowAttach(false)
      setPickPaymentId('')
      load()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Erreur')
    }
  }

  const detachPayment = async (paymentId) => {
    if (!confirm('Détacher ce paiement de la procédure ?')) return
    try {
      await api.delete(`/procedures/${procedure.id}/payments/${paymentId}`)
      load()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Erreur')
    }
  }

  const cancel = async () => {
    if (!confirm('Annuler cette procédure (statut « annulé ») ?')) return
    try {
      await api.post(`/procedures/${procedure.id}/cancel`)
      load()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Erreur')
    }
  }

  const remove = async () => {
    if (!confirm('Supprimer définitivement cette procédure ?')) return
    try {
      await api.delete(`/procedures/${procedure.id}`)
      navigate('/procedures')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Erreur')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <Link to="/procedures" className="text-sm text-blue-600 hover:underline">
            ← Procédures
          </Link>
          <h1 className="text-2xl font-bold text-gray-800 mt-1">
            {procedureTypeLabel(procedure.procedure_type)}
          </h1>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button className="btn-secondary" onClick={() => setShowEdit(true)}>✏️ Modifier</button>
          {procedure.status !== 'cancelled' && (
            <button className="btn-secondary" onClick={cancel}>Annuler la procédure</button>
          )}
          <button className="btn-danger" onClick={remove}>🗑️ Supprimer</button>
        </div>
      </div>

      <div className="card grid grid-cols-1 md:grid-cols-3 gap-4">
        <Field label="Bail">
          {lease ? (
            <Link to={`/leases/${lease.id}`} className="text-blue-600 hover:underline">
              {lease.property?.name} — {lease.tenant?.last_name} {lease.tenant?.first_name}
            </Link>
          ) : `Bail #${procedure.lease_id}`}
        </Field>
        <Field label="Notification">{fmtDate(procedure.notification_date)}</Field>
        <Field label="Échéance">
          {fmtDate(procedure.deadline_date)}
          {procedure.status !== 'paid' && procedure.status !== 'cancelled' && (
            <span className="ml-2 text-xs text-gray-500">
              ({procedure.days_remaining >= 0 ? `J-${procedure.days_remaining}` : `dépassée de ${-procedure.days_remaining} j`})
            </span>
          )}
        </Field>
        <Field label="Statut">
          <span className={procedureStatusClass(procedure.status)}>
            {procedureStatusLabel(procedure.status)}
          </span>
        </Field>
        <Field label="Huissier">{procedure.bailiff_name || '—'}</Field>
        <Field label="Référence d'acte">{procedure.act_reference || '—'}</Field>
      </div>

      <div className="card">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">Décomposition</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
          <Field label="Dette locative">{fmtCurrency(procedure.amount_rent)}</Field>
          <Field label="Frais d'huissier">{fmtCurrency(procedure.amount_fees)}</Field>
          <Field label="Autres">{fmtCurrency(procedure.amount_other)}</Field>
          <Field label="Total réclamé">
            <span className="font-semibold">{fmtCurrency(procedure.total_due)}</span>
          </Field>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4 border-t border-gray-100 pt-4 text-sm">
          <Field label="Réglé">{fmtCurrency(procedure.total_paid)}</Field>
          <Field label="Reste dû">
            {Number(procedure.remaining_due) > 0
              ? <span className="text-red-600 font-semibold">{fmtCurrency(procedure.remaining_due)}</span>
              : <span className="text-green-600 font-semibold">0,00 €</span>}
          </Field>
        </div>
      </div>

      {procedure.notes && (
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-700 mb-2">Notes</h2>
          <p className="text-sm text-gray-700 whitespace-pre-wrap">{procedure.notes}</p>
        </div>
      )}

      <div className="card p-0 overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div>
            <h2 className="text-sm font-semibold text-gray-700">Paiements rattachés</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Les paiements du bail dont la date tombe entre la notification et l'échéance
              sont rattachés automatiquement. Les autres peuvent l'être manuellement (ex.
              loyer payé entre la demande et la signification de l'acte).
            </p>
          </div>
          <button className="btn-primary btn-sm" onClick={() => setShowAttach(true)}>
            + Rattacher un paiement
          </button>
        </div>
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="table-th">Période</th>
              <th className="table-th">Date</th>
              <th className="table-th">Reçu</th>
              <th className="table-th">Source</th>
              <th className="table-th">Statut</th>
              <th className="table-th text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {attached.length === 0 && (
              <tr><td colSpan={6} className="table-td text-center text-gray-400 py-6">
                Aucun paiement rattaché
              </td></tr>
            )}
            {attached.map(({ payment, source }) => (
              <tr key={payment.id}>
                <td className="table-td">{MONTHS_FR[payment.month]} {payment.year}</td>
                <td className="table-td text-sm">{fmtDate(payment.payment_date)}</td>
                <td className="table-td">{fmtCurrency(payment.received_amount)}</td>
                <td className="table-td text-xs">
                  {source === 'auto'
                    ? <span className="px-2 py-0.5 rounded bg-blue-50 text-blue-700">Automatique</span>
                    : <span className="px-2 py-0.5 rounded bg-amber-50 text-amber-700">Manuel</span>}
                </td>
                <td className="table-td"><StatusBadge status={payment.status} /></td>
                <td className="table-td text-right">
                  {source === 'manual' && (
                    <button
                      className="btn-secondary btn-sm"
                      onClick={() => detachPayment(payment.id)}
                      title="Détacher"
                    >Détacher</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showEdit && (
        <ProcedureModal
          procedure={procedure}
          onClose={() => setShowEdit(false)}
          onSaved={() => { setShowEdit(false); load() }}
        />
      )}

      {showAttach && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6 space-y-4">
            <h3 className="text-lg font-semibold">Rattacher un paiement</h3>
            <p className="text-sm text-gray-600">
              Choisis un paiement existant de ce bail à imputer manuellement à la procédure.
            </p>
            <select
              className="form-input"
              value={pickPaymentId}
              onChange={(e) => setPickPaymentId(e.target.value)}
            >
              <option value="">— Sélectionner un paiement —</option>
              {candidates.map((p) => (
                <option key={p.id} value={p.id}>
                  {MONTHS_FR[p.month]} {p.year} · {fmtCurrency(p.received_amount)} · {fmtDate(p.payment_date)}
                </option>
              ))}
            </select>
            <div className="flex justify-end gap-2">
              <button className="btn-secondary" onClick={() => setShowAttach(false)}>Annuler</button>
              <button className="btn-primary" disabled={!pickPaymentId} onClick={attachPayment}>
                Rattacher
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
