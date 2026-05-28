import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import api from '../api'
import { useAuth } from '../AuthContext'
import StatusBadge from '../components/StatusBadge'
import AlertBanner from '../components/AlertBanner'
import Modal from '../components/Modal'
import PaymentModal from '../components/PaymentModal'
import BulkPaymentModal from '../components/BulkPaymentModal'
import PaymentEditModal from '../components/PaymentEditModal'
import {
  fmtCurrency, fmtDate, fmtDatetime, MONTHS_FR,
  docTypeLabel, currentYearMonth, leaseTypeLabel, revisionReasonLabel,
} from '../utils'

function ReceiptModal({ lease, onClose, onSaved }) {
  const { year: curYear, month: curMonth } = currentYearMonth()
  const [year, setYear] = useState(curYear)
  const [month, setMonth] = useState(curMonth)
  const [loading, setLoading] = useState(false)

  const generate = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      const r = await api.post(`/receipts/generate/${lease.id}?year=${year}&month=${month}`, null, { responseType: 'blob' })
      const url = URL.createObjectURL(r.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `quittance_${year}_${String(month).padStart(2, '0')}.pdf`
      a.click()
      URL.revokeObjectURL(url)
      toast.success('Quittance générée et téléchargée')
      onSaved()
    } catch {
      toast.error('Erreur lors de la génération')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal title="Générer une quittance de loyer" onClose={onClose}>
      <form onSubmit={generate} className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="form-label">Année</label>
            <input type="number" className="form-input" value={year} onChange={(e) => setYear(e.target.value)} required />
          </div>
          <div>
            <label className="form-label">Mois</label>
            <select className="form-input" value={month} onChange={(e) => setMonth(e.target.value)}>
              {MONTHS_FR.slice(1).map((m, i) => (
                <option key={i + 1} value={i + 1}>{m}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="flex justify-end gap-3">
          <button type="button" className="btn-secondary" onClick={onClose}>Annuler</button>
          <button type="submit" disabled={loading} className="btn-primary">
            {loading ? 'Génération…' : '📄 Générer PDF'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function RevisionModal({ lease, onClose, onSaved }) {
  const [effectiveFrom, setEffectiveFrom] = useState('')
  const [rent, setRent] = useState(lease.current_monthly_rent ?? lease.initial_monthly_rent ?? '')
  const [charges, setCharges] = useState(lease.current_monthly_charges ?? lease.initial_monthly_charges ?? '')
  const [reason, setReason] = useState('irl_revision')
  const [saving, setSaving] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      await api.post(`/leases/${lease.id}/revisions`, {
        effective_from: effectiveFrom,
        monthly_rent: rent,
        monthly_charges: charges,
        reason,
      })
      toast.success('Révision ajoutée')
      onSaved()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="Ajouter une révision de loyer" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="form-label">Date d'effet</label>
          <input type="date" className="form-input" value={effectiveFrom}
            onChange={(e) => setEffectiveFrom(e.target.value)} required />
          <p className="text-xs text-gray-400 mt-1">
            Le nouveau loyer s'applique à partir de cette date pour tous les mois suivants.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="form-label">Nouveau loyer HC (€)</label>
            <input type="number" step="0.01" className="form-input" value={rent}
              onChange={(e) => setRent(e.target.value)} required />
          </div>
          <div>
            <label className="form-label">Nouvelles charges (€)</label>
            <input type="number" step="0.01" className="form-input" value={charges}
              onChange={(e) => setCharges(e.target.value)} required />
          </div>
        </div>
        <div>
          <label className="form-label">Motif</label>
          <select className="form-input" value={reason} onChange={(e) => setReason(e.target.value)}>
            <option value="irl_revision">Révision IRL</option>
            <option value="amicable">Amiable</option>
            <option value="other">Autre</option>
          </select>
        </div>
        <div className="flex justify-end gap-3">
          <button type="button" className="btn-secondary" onClick={onClose}>Annuler</button>
          <button type="submit" disabled={saving} className="btn-primary">
            {saving ? 'Enregistrement…' : 'Enregistrer'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

export default function LeaseDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const canDelete = user?.role === 'admin' || user?.role === 'supervisor'
  const [lease, setLease] = useState(null)
  const [payments, setPayments] = useState([])
  const [documents, setDocuments] = useState([])
  const [revisions, setRevisions] = useState([])
  const [modal, setModal] = useState(null) // 'payment' | 'receipt' | 'revision' | 'bulk' | null
  const [editingPayment, setEditingPayment] = useState(null)
  const [paymentYearFilter, setPaymentYearFilter] = useState(String(new Date().getFullYear()))

  const loadAll = async () => {
    const [l, p, d, r] = await Promise.all([
      api.get(`/leases/${id}`),
      api.get('/payments', { params: { lease_id: id, page_size: 500 } }),
      api.get('/documents', { params: { lease_id: id } }),
      api.get(`/leases/${id}/revisions`),
    ])
    setLease(l.data); setPayments(p.data.items); setDocuments(d.data); setRevisions(r.data)
  }

  useEffect(() => { loadAll() }, [id])

  const deletePayment = async (payId) => {
    if (!confirm('Supprimer ce paiement ?')) return
    try {
      await api.delete(`/payments/${payId}`)
      toast.success('Paiement supprimé')
      loadAll()
    } catch { toast.error('Erreur') }
  }

  const deleteDoc = async (docId) => {
    if (!confirm('Supprimer ce document ?')) return
    try {
      await api.delete(`/documents/${docId}`)
      toast.success('Document supprimé')
      loadAll()
    } catch { toast.error('Erreur') }
  }

  const deleteRevision = async (revId) => {
    if (!confirm('Supprimer cette révision ?')) return
    try {
      await api.delete(`/leases/${id}/revisions/${revId}`)
      toast.success('Révision supprimée')
      loadAll()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    }
  }

  if (!lease) return <p className="text-gray-400">Chargement…</p>

  const today = new Date()
  const irl = lease.next_irl_revision_date ? new Date(lease.next_irl_revision_date) : null
  const irlAlert = irl && (irl - today) / 86400000 <= 30 && (irl - today) / 86400000 >= 0

  // Total dû — mirrors the dashboard's "Net outstanding" formula
  // (PROJECT.md "Net outstanding (all-months)"): max(0, Σexpected − Σreceived)
  // across every Payment row, plus the current month projected as unpaid if
  // no row exists for it (active leases only). Net of overpayments — surplus
  // on month M cancels arrears on earlier months, which a naive sum of
  // per-row `outstanding_balance` would not do (PROJECT.md L138-139).
  const currentYear = today.getFullYear()
  const currentMonth = today.getMonth() + 1
  const hasCurrentMonthPayment = payments.some(
    (p) => p.year === currentYear && p.month === currentMonth,
  )
  const currentMonthExpected = Number(lease.current_monthly_rent ?? 0)
                             + Number(lease.current_monthly_charges ?? 0)
  const projectCurrentMonth = lease.is_active
                            && !hasCurrentMonthPayment
                            && currentMonthExpected > 0
  const sumExpected = payments.reduce((acc, p) => acc + Number(p.expected_amount || 0), 0)
                    + (projectCurrentMonth ? currentMonthExpected : 0)
  const sumReceived = payments.reduce((acc, p) => acc + Number(p.received_amount || 0), 0)
  const totalDue = Math.max(0, sumExpected - sumReceived)
  let debtMonthsCount = payments.filter((p) => Number(p.outstanding_balance) > 0).length
  if (projectCurrentMonth) debtMonthsCount += 1

  // Payments sorted ASC for the history table + running cumulative net
  // outstanding (oldest first). Formula matches the dashboard's "Total dû"
  // (PROJECT.md "Net outstanding"): max(0, Σexpected − Σreceived) cumulated
  // across the full history, so an overpayment in one month reduces the
  // displayed cumulative against earlier arrears.
  const paymentsAsc = [...payments].sort((a, b) => {
    if (a.year !== b.year) return a.year - b.year
    return a.month - b.month
  })
  let runningExpected = 0
  let runningReceived = 0
  const paymentsWithCumAll = paymentsAsc.map((p) => {
    runningExpected += Number(p.expected_amount || 0)
    runningReceived += Number(p.received_amount || 0)
    return {
      ...p,
      cumulative_outstanding: Math.max(0, runningExpected - runningReceived),
    }
  })

  // Years present in this lease's payment history.
  const paymentYears = Array.from(new Set(payments.map((p) => p.year))).sort((a, b) => b - a)
  const paymentsWithCum = paymentsWithCumAll.filter((p) =>
    paymentYearFilter === 'all' || String(p.year) === paymentYearFilter
  )

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/leases" className="btn-secondary btn-sm">← Retour</Link>
        <h1 className="text-2xl font-bold text-gray-800">Bail — {lease.property?.name}</h1>
      </div>

      {/* Alerts */}
      {irlAlert && (
        <AlertBanner type="warning">
          Révision IRL anniversaire le {fmtDate(lease.next_irl_revision_date)} — dans moins de 30 jours.
          Ajoutez une révision dans "Historique des loyers" avec la nouvelle valeur.
        </AlertBanner>
      )}
      {lease.notice_period_open && (
        <AlertBanner type="danger">
          Le bail prend fin le {fmtDate(lease.end_date)} — préavis bailleur possible.
        </AlertBanner>
      )}

      {/* Total dû summary — visible at the top so the landlord sees the
          cumulative debt before scrolling to the payment history. */}
      <div className={`card border-t-4 ${totalDue > 0 ? 'border-red-600 bg-red-50' : 'border-green-500 bg-green-50'}`}>
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <p className="text-sm text-gray-600 font-semibold">Total dû par ce locataire</p>
            <p className={`text-3xl font-extrabold mt-1 ${totalDue > 0 ? 'text-red-700' : 'text-green-700'}`}>
              {fmtCurrency(totalDue)}
            </p>
            <p className="text-xs text-gray-500 mt-1">
              Solde net sur l'ensemble du bail : Σ attendu − Σ reçu, incluant le mois courant
              projeté si non encore enregistré. Les trop-perçus compensent les arriérés.
            </p>
          </div>
          <div className="text-right">
            <p className="text-sm text-gray-600">Nombre de mois concernés</p>
            <p className={`text-2xl font-bold ${debtMonthsCount > 0 ? 'text-red-700' : 'text-green-700'}`}>
              {debtMonthsCount}
            </p>
          </div>
        </div>
      </div>

      {/* Lease info */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card space-y-2">
          <h2 className="font-semibold text-gray-700">Bien</h2>
          <p className="text-gray-900">{lease.property?.name}</p>
          <p className="text-sm text-gray-500">{lease.property?.address_street}, {lease.property?.address_zip} {lease.property?.address_city}</p>
        </div>
        <div className="card space-y-2">
          <h2 className="font-semibold text-gray-700">Locataire</h2>
          <p className="text-gray-900">{lease.tenant?.first_name} {lease.tenant?.last_name}</p>
          {lease.tenant?.email && <p className="text-sm text-gray-500">{lease.tenant.email}</p>}
          {lease.tenant?.phone && <p className="text-sm text-gray-500">{lease.tenant.phone}</p>}
          {lease.tenant?.guarantor_name && <p className="text-sm text-gray-500">Garant : {lease.tenant.guarantor_name}</p>}
        </div>
        <div className="card space-y-2">
          <h2 className="font-semibold text-gray-700">Conditions financières (initiales)</h2>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <span className="text-gray-500">Loyer HC</span><span className="font-medium">{fmtCurrency(lease.initial_monthly_rent ?? 0)}</span>
            <span className="text-gray-500">Provisions charges</span><span className="font-medium">{fmtCurrency(lease.initial_monthly_charges ?? 0)}</span>
            {/* When a revision is in effect, the initial Total CC is shown
                neutral (it's the historical reference, not the current
                figure); the blue/bold emphasis moves to "Loyer CC actuel".
                Without a revision, Total CC keeps the emphasis. */}
            <span className="text-gray-500">Total CC</span>
            <span className={
              (lease.current_monthly_total != null
                && Number(lease.current_monthly_total) !== Number(lease.initial_monthly_total))
                ? "font-semibold"
                : "font-semibold text-blue-700"
            }>
              {fmtCurrency(lease.initial_monthly_total ?? 0)}
            </span>
            {lease.current_monthly_total != null && Number(lease.current_monthly_total) !== Number(lease.initial_monthly_total) && <>
              <span className="text-gray-500">
                Loyer CC actuel <span className="text-xs text-gray-400">(révisé)</span>
              </span>
              <span className="font-semibold text-blue-700">{fmtCurrency(lease.current_monthly_total)}</span>
            </>}
            {lease.security_deposit_amount && <>
              <span className="text-gray-500">Dépôt de garantie</span><span>{fmtCurrency(lease.security_deposit_amount)}</span>
            </>}
          </div>
          <p className="text-xs text-gray-400">
            Ces valeurs proviennent de la révision "Initiale" — modifier le bail les met à jour partout.
          </p>
        </div>
        <div className="card space-y-2">
          <h2 className="font-semibold text-gray-700">Dates & type</h2>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <span className="text-gray-500">Type de bail</span>
            <span className="font-medium">
              {leaseTypeLabel(lease.lease_type)}
              {lease.is_amendment && <span className="ml-1 text-xs text-gray-400">(hérité)</span>}
            </span>
            <span className="text-gray-500">Début</span><span>{fmtDate(lease.start_date)}</span>
            <span className="text-gray-500">Fin {lease.is_amendment ? '(héritée du bail parent)' : '(calculée)'}</span>
            <span>{fmtDate(lease.end_date)}</span>
            <span className="text-gray-500">Prochaine révision IRL</span><span>{fmtDate(lease.next_irl_revision_date)}</span>
            <span className="text-gray-500">Bail actif</span>
            <span>{lease.is_active ? 'Oui' : 'Non (résilié)'}</span>
          </div>
          {lease.is_amendment && lease.parent_lease && (
            <p className="text-xs text-gray-500 pt-1">
              Avenant du bail :{' '}
              <Link to={`/leases/${lease.parent_lease.id}`} className="text-blue-600 hover:underline">
                {lease.parent_lease.tenant_last_name} {lease.parent_lease.tenant_first_name} — début {fmtDate(lease.parent_lease.start_date)}
              </Link>
            </p>
          )}
        </div>
      </div>

      {/* Amendments (only on parent leases that have children) */}
      {lease.amendments && lease.amendments.length > 0 && (
        <div className="card">
          <h2 className="text-lg font-semibold text-gray-800 mb-3">Avenants</h2>
          <ul className="divide-y divide-gray-100">
            {lease.amendments.map((a) => (
              <li key={a.id} className="py-2 flex items-center justify-between">
                <div>
                  <Link to={`/leases/${a.id}`} className="text-blue-600 hover:underline font-medium">
                    {a.tenant_last_name} {a.tenant_first_name}
                  </Link>
                  <span className="ml-2 text-xs text-gray-500">
                    début {fmtDate(a.start_date)} · fin {fmtDate(a.end_date)}
                  </span>
                  {!a.is_active && <span className="ml-2 text-xs text-gray-400">(résilié)</span>}
                </div>
                <div className="text-sm text-gray-700">
                  {a.current_monthly_total != null ? fmtCurrency(a.current_monthly_total) : '—'}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Rent history */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-800">Historique des loyers</h2>
          <button className="btn-primary btn-sm" onClick={() => setModal('revision')}>+ Ajouter une révision</button>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="table-th">Date d'effet</th>
                <th className="table-th">Loyer HC</th>
                <th className="table-th">Charges</th>
                <th className="table-th">Total CC</th>
                <th className="table-th">Motif</th>
                <th className="table-th text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {revisions.length === 0 && (
                <tr><td colSpan={6} className="table-td text-center text-gray-400 py-6">Aucune révision</td></tr>
              )}
              {revisions.map((r) => (
                <tr key={r.id} className="hover:bg-gray-50">
                  <td className="table-td font-medium">{fmtDate(r.effective_from)}</td>
                  <td className="table-td">{fmtCurrency(r.monthly_rent)}</td>
                  <td className="table-td">{fmtCurrency(r.monthly_charges)}</td>
                  <td className="table-td font-semibold text-blue-700">
                    {fmtCurrency(Number(r.monthly_rent) + Number(r.monthly_charges))}
                  </td>
                  <td className="table-td text-sm">{revisionReasonLabel(r.reason)}</td>
                  <td className="table-td text-right">
                    {r.reason !== 'initial' && (
                      <button className="btn-danger btn-sm" onClick={() => deleteRevision(r.id)}>🗑</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Payments */}
      <div className="card">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <h2 className="text-lg font-semibold text-gray-800">Historique des paiements</h2>
          <div className="flex gap-2 flex-wrap items-center">
            <select
              className="form-input form-input-sm w-32 py-1"
              value={paymentYearFilter}
              onChange={(e) => setPaymentYearFilter(e.target.value)}
              title="Filtrer par année"
            >
              <option value="all">Toutes années</option>
              {paymentYears.map((y) => (
                <option key={y} value={String(y)}>{y}</option>
              ))}
            </select>
            <button className="btn-secondary btn-sm" onClick={() => setModal('bulk')}>Saisir des périodes passées</button>
            <button className="btn-secondary btn-sm" onClick={() => setModal('receipt')}>📄 Quittance PDF</button>
            <button className="btn-primary btn-sm" onClick={() => setModal('payment')}>+ Saisir un paiement</button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="table-th">Période</th>
                <th className="table-th">Attendu</th>
                <th className="table-th">Reçu</th>
                <th className="table-th">Solde dû</th>
                <th className="table-th">Solde cumulé</th>
                <th className="table-th">Statut</th>
                <th className="table-th">Date</th>
                <th className="table-th">Notes</th>
                <th className="table-th text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {paymentsWithCum.length === 0 && (
                <tr><td colSpan={9} className="table-td text-center text-gray-400 py-6">Aucun paiement enregistré</td></tr>
              )}
              {paymentsWithCum.map((p) => (
                <tr key={p.id} className="hover:bg-gray-50">
                  <td className="table-td font-medium">{MONTHS_FR[p.month]} {p.year}</td>
                  <td className="table-td">{fmtCurrency(p.expected_amount)}</td>
                  <td className="table-td">{fmtCurrency(p.received_amount)}</td>
                  <td className="table-td">
                    {Number(p.outstanding_balance) > 0
                      ? <span className="text-red-600 font-medium">{fmtCurrency(p.outstanding_balance)}</span>
                      : <span className="text-green-600">0,00 €</span>}
                  </td>
                  <td className="table-td">
                    {Number(p.cumulative_outstanding) > 0
                      ? <span className="text-red-700 font-semibold">{fmtCurrency(p.cumulative_outstanding)}</span>
                      : <span className="text-green-600">{fmtCurrency(0)}</span>}
                  </td>
                  <td className="table-td"><StatusBadge status={p.status} /></td>
                  <td className="table-td text-sm">{fmtDate(p.payment_date)}</td>
                  <td className="table-td text-xs text-gray-500 max-w-[150px] truncate">{p.notes || ''}</td>
                  <td className="table-td text-right space-x-1">
                    <button className="btn-secondary btn-sm" title="Modifier" onClick={() => setEditingPayment(p)}>✏️</button>
                    {canDelete && (
                      <button className="btn-danger btn-sm" title="Supprimer" onClick={() => deletePayment(p.id)}>🗑</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Documents */}
      <div className="card">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Documents</h2>
        {documents.length === 0
          ? <p className="text-gray-400 text-sm">Aucun document</p>
          : (
            <ul className="divide-y divide-gray-100">
              {documents.map((d) => (
                <li key={d.id} className="flex items-center justify-between py-2">
                  <div>
                    <span className="text-sm font-medium text-gray-800">{d.file_name}</span>
                    <span className="ml-2 text-xs text-gray-400">{docTypeLabel(d.type)}</span>
                    <span className="ml-2 text-xs text-gray-300">{fmtDatetime(d.upload_date)}</span>
                  </div>
                  <div className="flex gap-2">
                    <a href={`/rental/api/documents/${d.id}/download`} target="_blank" rel="noreferrer" className="btn-secondary btn-sm">⬇️ Télécharger</a>
                    <button className="btn-danger btn-sm" onClick={() => deleteDoc(d.id)}>🗑</button>
                  </div>
                </li>
              ))}
            </ul>
          )}
      </div>

      {modal === 'payment' && (
        <PaymentModal lease={lease} onClose={() => setModal(null)} onSaved={() => { setModal(null); loadAll() }} />
      )}
      {modal === 'receipt' && (
        <ReceiptModal lease={lease} onClose={() => setModal(null)} onSaved={() => { setModal(null); loadAll() }} />
      )}
      {modal === 'revision' && (
        <RevisionModal lease={lease} onClose={() => setModal(null)} onSaved={() => { setModal(null); loadAll() }} />
      )}
      {modal === 'bulk' && (
        <BulkPaymentModal lease={lease} onClose={() => setModal(null)} onSaved={() => { setModal(null); loadAll() }} />
      )}
      {editingPayment && (
        <PaymentEditModal
          payment={editingPayment}
          onClose={() => setEditingPayment(null)}
          onSaved={() => { setEditingPayment(null); loadAll() }}
        />
      )}
    </div>
  )
}
