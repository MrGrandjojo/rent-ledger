import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import api from '../api'
import { useAuth } from '../AuthContext'
import PaymentModal from '../components/PaymentModal'
import BulkPaymentModal from '../components/BulkPaymentModal'
import PaymentEditModal from '../components/PaymentEditModal'
import StatusBadge from '../components/StatusBadge'
import { fmtCurrency, fmtDate, MONTHS_FR } from '../utils'

const PAGE_SIZE_OPTIONS = [25, 50, 100, 200]

export default function Payments() {
  const { user } = useAuth()
  const canDelete = user?.role === 'admin' || user?.role === 'supervisor'
  const [payments, setPayments] = useState([])
  const [leases, setLeases] = useState([])
  const [leaseFilter, setLeaseFilter] = useState('')
  const [yearFilter, setYearFilter] = useState(String(new Date().getFullYear()))
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [showBulk, setShowBulk] = useState(false)
  const [editingPayment, setEditingPayment] = useState(null)

  // Filter changes reset the page in the SAME state batch as the filter
  // update (via the handlers below), so by the time this effect fires
  // there's only ever one fetch in flight with consistent params. The
  // AbortController guards against a slow earlier fetch overwriting the
  // results of a newer one (e.g. user clicks Next twice quickly).
  useEffect(() => {
    const ctrl = new AbortController()
    const params = { page, page_size: pageSize }
    if (leaseFilter) params.lease_id = leaseFilter
    if (yearFilter && yearFilter !== 'all') params.year = yearFilter
    Promise.all([
      api.get('/payments', { params, signal: ctrl.signal }),
      api.get('/leases', { signal: ctrl.signal }),
    ])
      .then(([p, l]) => {
        setPayments(p.data.items)
        setTotal(p.data.total)
        setLeases(l.data)
        setLoading(false)
      })
      .catch((err) => {
        if (err.name === 'CanceledError' || err.name === 'AbortError') return
        throw err
      })
    return () => ctrl.abort()
  }, [page, pageSize, leaseFilter, yearFilter])

  // Apply filter + reset page in the SAME state batch — React 18
  // batches multiple setState calls inside a single event handler, so
  // the data effect runs once with both new values rather than twice
  // (which would race: stale page + new filter, then new page + new
  // filter, with the first request sometimes finishing last).
  const onYearChange = (v) => { setYearFilter(v); setPage(1) }
  const onLeaseChange = (v) => { setLeaseFilter(v); setPage(1) }
  const onPageSizeChange = (v) => { setPageSize(v); setPage(1) }

  const reload = () => {
    // Triggered after a write (delete/create/edit) — re-runs the data
    // effect by tweaking a counter would be cleaner, but simply
    // re-fetching via the same params is enough.
    const params = { page, page_size: pageSize }
    if (leaseFilter) params.lease_id = leaseFilter
    if (yearFilter && yearFilter !== 'all') params.year = yearFilter
    Promise.all([api.get('/payments', { params }), api.get('/leases')])
      .then(([p, l]) => {
        setPayments(p.data.items)
        setTotal(p.data.total)
        setLeases(l.data)
      })
  }

  const deletePayment = async (p) => {
    if (!confirm(`Supprimer le paiement de ${MONTHS_FR[p.month]} ${p.year} ?`)) return
    try {
      await api.delete(`/payments/${p.id}`)
      toast.success('Paiement supprimé')
      reload()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    }
  }

  // Year dropdown: current year + 5 past years. No future years — payments
  // for months that haven't happened yet aren't recorded, so offering them
  // in the filter would always return empty results.
  const currentYear = new Date().getFullYear()
  const years = Array.from({ length: 6 }, (_, i) => currentYear - i)

  const leaseLabel = (id) => {
    const l = leases.find((x) => x.id === id)
    return l ? `${l.property?.name} — ${l.tenant?.last_name}` : `Bail #${id}`
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  if (loading) return <p className="text-gray-400">Chargement…</p>

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-gray-800">Paiements</h1>
        <div className="flex items-center gap-3 flex-wrap">
          <select
            className="form-input w-32"
            value={yearFilter}
            onChange={(e) => onYearChange(e.target.value)}
            title="Filtrer par année"
          >
            <option value="all">Toutes années</option>
            {years.map((y) => (
              <option key={y} value={String(y)}>{y}</option>
            ))}
          </select>
          <select className="form-input w-64" value={leaseFilter} onChange={(e) => onLeaseChange(e.target.value)}>
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
            {payments.length === 0 && (
              <tr><td colSpan={8} className="table-td text-center text-gray-400 py-8">Aucun paiement</td></tr>
            )}
            {payments.map((p) => (
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
                  {canDelete && (
                    <button
                      className="btn-danger btn-sm"
                      title="Supprimer ce paiement"
                      onClick={() => deletePayment(p)}
                    >🗑</button>
                  )}
                  <Link to={`/leases/${p.lease_id}`} className="btn-secondary btn-sm">Voir bail</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between flex-wrap gap-3 text-sm text-gray-600">
        <div>
          {total > 0
            ? <>Affichage de <strong>{(page - 1) * pageSize + 1}</strong>–<strong>{Math.min(page * pageSize, total)}</strong> sur <strong>{total}</strong> paiements</>
            : '0 résultat'}
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500">Par page</label>
          <select
            className="form-input w-20"
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
          >
            {PAGE_SIZE_OPTIONS.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          <button
            className="btn-secondary btn-sm"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >‹ Précédent</button>
          <span className="text-gray-500">Page {page} / {totalPages}</span>
          <button
            className="btn-secondary btn-sm"
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
          >Suivant ›</button>
        </div>
      </div>

      {showModal && (
        <PaymentModal
          leases={leases}
          onClose={() => setShowModal(false)}
          onSaved={() => { setShowModal(false); reload() }}
        />
      )}
      {showBulk && (
        <BulkPaymentModal
          leases={leases}
          onClose={() => setShowBulk(false)}
          onSaved={() => { setShowBulk(false); reload() }}
        />
      )}
      {editingPayment && (
        <PaymentEditModal
          payment={editingPayment}
          onClose={() => setEditingPayment(null)}
          onSaved={() => { setEditingPayment(null); reload() }}
        />
      )}
    </div>
  )
}
