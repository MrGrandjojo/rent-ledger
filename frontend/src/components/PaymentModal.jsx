import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import api from '../api'
import Modal from './Modal'
import { MONTHS_FR, currentYearMonth } from '../utils'

/**
 * Payment creation modal.
 *
 * Two modes:
 *   - lease known (lease prop given): hides the lease dropdown.
 *   - lease not yet known (leases prop given): shows a "Bail" dropdown at the
 *     top. Once selected, the rest of the form behaves identically.
 *
 * The "Montant attendu" field is fetched from the backend each time the
 * lease, year, or month changes, using the rent_revision in effect for the
 * selected (year, month).
 */
export default function PaymentModal({ lease = null, leases = null, onClose, onSaved }) {
  const { year: curYear, month: curMonth } = currentYearMonth()
  const [selectedLeaseId, setSelectedLeaseId] = useState(lease ? lease.id : '')
  const [year, setYear] = useState(curYear)
  const [month, setMonth] = useState(curMonth)
  const [expectedAmount, setExpectedAmount] = useState('')
  const [receivedAmount, setReceivedAmount] = useState('')
  const [paymentDate, setPaymentDate] = useState(new Date().toISOString().slice(0, 10))
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [loadingExpected, setLoadingExpected] = useState(false)

  // Recompute expected amount whenever lease / year / month changes
  useEffect(() => {
    if (!selectedLeaseId) {
      setExpectedAmount('')
      return
    }
    setLoadingExpected(true)
    api
      .get('/payments/expected', {
        params: { lease_id: selectedLeaseId, year, month },
      })
      .then((r) => setExpectedAmount(Number(r.data.expected_amount)))
      .catch(() => setExpectedAmount(''))
      .finally(() => setLoadingExpected(false))
  }, [selectedLeaseId, year, month])

  const submit = async (e) => {
    e.preventDefault()
    if (!selectedLeaseId) {
      toast.error('Sélectionnez un bail')
      return
    }
    setSaving(true)
    try {
      await api.post('/payments', {
        lease_id: Number(selectedLeaseId),
        year: Number(year),
        month: Number(month),
        expected_amount: expectedAmount,
        received_amount: receivedAmount || 0,
        payment_date: paymentDate || null,
        notes: notes || null,
      })
      toast.success('Paiement enregistré')
      onSaved()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const leaseLabel = (l) =>
    `${l.property?.name ?? `Bien #${l.property_id}`} — ${l.tenant?.last_name ?? ''} ${l.tenant?.first_name ?? ''}`

  return (
    <Modal title="Saisir un paiement" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        {leases && (
          <div>
            <label className="form-label">Bail</label>
            <select
              className="form-input"
              value={selectedLeaseId}
              onChange={(e) => setSelectedLeaseId(e.target.value)}
              required
            >
              <option value="">— Sélectionner un bail —</option>
              {leases.map((l) => (
                <option key={l.id} value={l.id}>{leaseLabel(l)}</option>
              ))}
            </select>
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="form-label">Année</label>
            <input
              type="number" className="form-input"
              value={year} onChange={(e) => setYear(e.target.value)} required
            />
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
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="form-label">
              Montant attendu (€)
              {loadingExpected && <span className="ml-2 text-xs text-gray-400">…calcul</span>}
            </label>
            <input
              type="number" step="0.01" className="form-input"
              value={expectedAmount}
              onChange={(e) => setExpectedAmount(e.target.value)} required
            />
            <p className="text-xs text-gray-400 mt-1">
              Calculé d'après la révision de loyer en vigueur pour la période sélectionnée.
            </p>
          </div>
          <div>
            <label className="form-label">Montant reçu (€)</label>
            <input
              type="number" step="0.01" className="form-input"
              value={receivedAmount}
              onChange={(e) => setReceivedAmount(e.target.value)} required
            />
          </div>
        </div>
        <div>
          <label className="form-label">Date de paiement</label>
          <input
            type="date" className="form-input"
            value={paymentDate}
            onChange={(e) => setPaymentDate(e.target.value)}
          />
        </div>
        <div>
          <label className="form-label">Notes</label>
          <textarea
            className="form-input" rows={2}
            value={notes} onChange={(e) => setNotes(e.target.value)}
          />
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
