import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import api from '../api'
import Modal from './Modal'
import { addMonthsISO } from '../utils'

/**
 * Procedure creation/edition modal — currently only "commandement de payer".
 *
 * On create with notification_date set, the deadline auto-fills to +2 months
 * (clampable / editable). On edit, fields are seeded from the existing row.
 */
export default function ProcedureModal({
  leases = null, lease = null, procedure = null,
  onClose, onSaved,
}) {
  const isEdit = !!procedure
  const today = new Date().toISOString().slice(0, 10)

  const [selectedLeaseId, setSelectedLeaseId] = useState(
    procedure?.lease_id ?? lease?.id ?? ''
  )
  const [notificationDate, setNotificationDate] = useState(
    procedure?.notification_date ?? today
  )
  const [deadlineDate, setDeadlineDate] = useState(
    procedure?.deadline_date ?? addMonthsISO(today, 2)
  )
  // The user may want a non-default deadline (e.g. an "huissier" notified the
  // tenant with a different delay). We auto-recompute the deadline only when
  // the user has NOT manually edited the field.
  const [deadlineTouched, setDeadlineTouched] = useState(isEdit)

  const [amountRent, setAmountRent]   = useState(procedure?.amount_rent  ?? '')
  const [amountFees, setAmountFees]   = useState(procedure?.amount_fees  ?? '')
  const [amountOther, setAmountOther] = useState(procedure?.amount_other ?? '')
  const [bailiffName, setBailiffName] = useState(procedure?.bailiff_name ?? '')
  const [actReference, setActReference] = useState(procedure?.act_reference ?? '')
  const [notes, setNotes] = useState(procedure?.notes ?? '')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!deadlineTouched && notificationDate) {
      setDeadlineDate(addMonthsISO(notificationDate, 2))
    }
  }, [notificationDate, deadlineTouched])

  const leaseLabel = (l) =>
    `${l.property?.name ?? `Bien #${l.property_id}`} — ${l.tenant?.last_name ?? ''} ${l.tenant?.first_name ?? ''}`

  const submit = async (e) => {
    e.preventDefault()
    if (!isEdit && !selectedLeaseId) {
      toast.error('Sélectionnez un bail')
      return
    }
    if (deadlineDate < notificationDate) {
      toast.error('L\'échéance ne peut pas précéder la date de notification')
      return
    }
    setSaving(true)
    try {
      const payload = {
        notification_date: notificationDate,
        deadline_date: deadlineDate,
        amount_rent:  amountRent  || 0,
        amount_fees:  amountFees  || 0,
        amount_other: amountOther || 0,
        bailiff_name: bailiffName || null,
        act_reference: actReference || null,
        notes: notes || null,
      }
      if (isEdit) {
        await api.put(`/procedures/${procedure.id}`, payload)
        toast.success('Procédure mise à jour')
      } else {
        await api.post('/procedures', {
          lease_id: Number(selectedLeaseId),
          procedure_type: 'commandement_payer',
          ...payload,
        })
        toast.success('Procédure créée')
      }
      onSaved()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const totalDue =
    (Number(amountRent)  || 0)
    + (Number(amountFees) || 0)
    + (Number(amountOther) || 0)

  return (
    <Modal
      title={isEdit ? 'Modifier le commandement de payer' : 'Nouveau commandement de payer'}
      onClose={onClose}
    >
      <form onSubmit={submit} className="space-y-4">
        {!isEdit && leases && !lease && (
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
            <label className="form-label">Date de notification</label>
            <input
              type="date" className="form-input"
              value={notificationDate}
              onChange={(e) => setNotificationDate(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="form-label">
              Échéance
              {!deadlineTouched && (
                <span className="ml-2 text-xs text-gray-400">(auto +2 mois)</span>
              )}
            </label>
            <input
              type="date" className="form-input"
              value={deadlineDate}
              onChange={(e) => { setDeadlineTouched(true); setDeadlineDate(e.target.value) }}
              required
            />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="form-label">Dette locative (€)</label>
            <input
              type="number" step="0.01" min="0" className="form-input"
              value={amountRent} onChange={(e) => setAmountRent(e.target.value)}
              placeholder="0.00"
            />
            <p className="text-xs text-gray-400 mt-1">Loyers et charges dus.</p>
          </div>
          <div>
            <label className="form-label">Frais d'huissier (€)</label>
            <input
              type="number" step="0.01" min="0" className="form-input"
              value={amountFees} onChange={(e) => setAmountFees(e.target.value)}
              placeholder="0.00"
            />
          </div>
          <div>
            <label className="form-label">Autres (€)</label>
            <input
              type="number" step="0.01" min="0" className="form-input"
              value={amountOther} onChange={(e) => setAmountOther(e.target.value)}
              placeholder="0.00"
            />
            <p className="text-xs text-gray-400 mt-1">Indemnités, etc.</p>
          </div>
        </div>

        <div className="bg-gray-50 rounded-lg p-3 text-sm flex justify-between">
          <span className="text-gray-600">Total réclamé</span>
          <span className="font-semibold text-gray-800">
            {totalDue.toLocaleString('fr-FR', { minimumFractionDigits: 2 })} €
          </span>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="form-label">Huissier (optionnel)</label>
            <input
              type="text" className="form-input"
              value={bailiffName} onChange={(e) => setBailiffName(e.target.value)}
              placeholder="Nom de l'étude"
            />
          </div>
          <div>
            <label className="form-label">Référence d'acte (optionnel)</label>
            <input
              type="text" className="form-input"
              value={actReference} onChange={(e) => setActReference(e.target.value)}
            />
          </div>
        </div>

        <div>
          <label className="form-label">Notes</label>
          <textarea
            className="form-input" rows={2}
            value={notes} onChange={(e) => setNotes(e.target.value)}
          />
        </div>

        <div className="flex justify-end gap-3">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Annuler
          </button>
          <button type="submit" disabled={saving} className="btn-primary">
            {saving ? 'Enregistrement…' : isEdit ? 'Mettre à jour' : 'Créer'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
