import { useState } from 'react'
import toast from 'react-hot-toast'
import api from '../api'
import Modal from './Modal'
import { fmtCurrency, MONTHS_FR } from '../utils'

/**
 * Edit an existing Payment record.
 *
 * "Montant attendu" is read-only — it is computed server-side from the
 * rent_revision in effect for the (year, month) of the payment, and must
 * never be manually overridden. The user can change received_amount,
 * payment_date (nullable), and notes; the backend recomputes status and
 * outstanding_balance on the fly.
 */
export default function PaymentEditModal({ payment, onClose, onSaved }) {
  const [receivedAmount, setReceivedAmount] = useState(String(payment.received_amount ?? 0))
  const [paymentDate, setPaymentDate] = useState(payment.payment_date || '')
  const [notes, setNotes] = useState(payment.notes || '')
  const [saving, setSaving] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      await api.put(`/payments/${payment.id}`, {
        received_amount: receivedAmount === '' ? 0 : Number(receivedAmount),
        payment_date: paymentDate || null,
        notes: notes || null,
      })
      toast.success('Paiement mis à jour')
      onSaved()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title={`Modifier le paiement — ${MONTHS_FR[payment.month]} ${payment.year}`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="form-label">Montant attendu (€)</label>
          <input
            type="text"
            className="form-input bg-gray-100 cursor-not-allowed"
            value={fmtCurrency(payment.expected_amount)}
            readOnly
            disabled
          />
          <p className="text-xs text-gray-400 mt-1">
            Calculé d'après la révision de loyer en vigueur — non modifiable.
          </p>
        </div>
        <div>
          <label className="form-label">Montant reçu (€)</label>
          <input
            type="number" step="0.01" className="form-input"
            value={receivedAmount}
            onChange={(e) => setReceivedAmount(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="form-label">Date de paiement</label>
          <input
            type="date" className="form-input"
            value={paymentDate || ''}
            onChange={(e) => setPaymentDate(e.target.value)}
          />
          <p className="text-xs text-gray-400 mt-1">
            Laisser vide si le paiement n'a pas encore été reçu.
          </p>
        </div>
        <div>
          <label className="form-label">Notes</label>
          <textarea
            className="form-input" rows={3}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>
        <div className="flex justify-end gap-3 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Annuler</button>
          <button type="submit" disabled={saving} className="btn-primary">
            {saving ? 'Enregistrement…' : 'Enregistrer'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
