import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'
import PaymentModal from '../components/PaymentModal'
import BulkPaymentModal from '../components/BulkPaymentModal'
import PaymentEditModal from '../components/PaymentEditModal'
import StatusBadge from '../components/StatusBadge'
import { fmtCurrency, fmtDate, MONTHS_FR } from '../utils'

export default function Payments() {
  const [payments, setPayments] = useState([])
  const [leases, setLeases] = useState([])
  const [leaseFilter, setLeaseFilter] = useState('')
  const [yearFilter, setYearFilter] = useState(String(new Date().getFullYear()))
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [showBulk, setShowBulk] = useState(false)
  const [editingPayment, setEditingPayment] = useState(null)

  const load = async () => {
    const [p, l] = await Promise.all([api.get('/payments'), api.get('/leases')])
    setPayments(p.data)
    setLeases(l.data)
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  // Years present in the data — sorted DESC, plus a sentinel "all".
  const years = Array.from(new Set(payments.map((p) => p.year))).sort((a, b) => b - a)

  const filtered = payments.filter((p) => {
    if (leaseFilter && String(p.lease_id) !== leaseFilter) return false
    if (yearFilter && yearFilter !== 'all' && String(p.year) !== yearFilter) return false
    return true
  })

  const leaseLabel = (id) => {
    const l = leases.find((x) => x.id === id)
    return l ? `${l.property?.name} — ${l.tenant?.last_name}` : `Bail #${id}`
  }

  if (loading) return <p className="text-gray-400">Chargement…</p>

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-gray-800">Paiements</h1>
        <div className="flex items-center gap-3 flex-wrap">
          <select
            className="form-input w-32"
            value={yearFilter}
            onChange={(e) => setYearFilter(e.target.value)}
            title="Filtrer par année"
          >
            <option value="all">Toutes années</option>
            {years.map((y) => (
              <option key={y} value={String(y)}>{y}</option>
            ))}
          </select>
          <select className="form-input w-64" value={leaseFilter} onChange={(e) => setLeaseFilter(e.target.value)}>
            <option value="">Tous les baux</option>
            {leases.map((l) => (
              <option key={l.id} value={l.id}>{l.property?.name} — {l.tenant?.last_name}</option>
            ))}
          </select>
          <button className="btn-secondary" onClick={() => setShowBulk(true)}>Saisie groupée</button>
          <button className="btn-primary" onClick={() => setShowModal(true)}>+ Ajouter un paiement</button>
        </div>
      </div>

      <div className="card p-0 overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="table-th">Bail</th>
              <th className="table-th">Période</th>
              <th className="table-th">Attendu</th>
              <th className="table-th">Reçu</th>
              <th className="table-th">Solde dû</th>
              <th className="table-th">Statut</th>
              <th className="table-th">Date</th>
              <th className="table-th text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.length === 0 && (
              <tr><td colSpan={8} className="table-td text-center text-gray-400 py-8">Aucun paiement</td></tr>
            )}
            {filtered.map((p) => (
              <tr key={p.id} className="hover:bg-gray-50">
                <td className="table-td text-sm">{leaseLabel(p.lease_id)}</td>
                <td className="table-td font-medium">{MONTHS_FR[p.month]} {p.year}</td>
                <td className="table-td">{fmtCurrency(p.expected_amount)}</td>
                <td className="table-td">{fmtCurrency(p.received_amount)}</td>
                <td className="table-td">
                  {Number(p.outstanding_balance) > 0
                    ? <span className="text-red-600 font-medium">{fmtCurrency(p.outstanding_balance)}</span>
                    : <span className="text-green-600">0,00 €</span>}
                </td>
                <td className="table-td"><StatusBadge status={p.status} /></td>
                <td className="table-td text-sm">{fmtDate(p.payment_date)}</td>
                <td className="table-td text-right space-x-1 whitespace-nowrap">
                  <button
                    className="btn-secondary btn-sm"
                    title="Modifier ce paiement"
                    onClick={() => setEditingPayment(p)}
                  >
                    ✏️
                  </button>
                  <Link to={`/leases/${p.lease_id}`} className="btn-secondary btn-sm">Voir bail</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showModal && (
        <PaymentModal
          leases={leases}
          onClose={() => setShowModal(false)}
          onSaved={() => { setShowModal(false); load() }}
        />
      )}
      {showBulk && (
        <BulkPaymentModal
          leases={leases}
          onClose={() => setShowBulk(false)}
          onSaved={() => { setShowBulk(false); load() }}
        />
      )}
      {editingPayment && (
        <PaymentEditModal
          payment={editingPayment}
          onClose={() => setEditingPayment(null)}
          onSaved={() => { setEditingPayment(null); load() }}
        />
      )}
    </div>
  )
}
