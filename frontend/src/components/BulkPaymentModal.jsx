import { useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import api from '../api'
import Modal from './Modal'
import { MONTHS_FR, fmtCurrency, currentYearMonth } from '../utils'

/**
 * Saisie groupée — bulk retroactive payment entry.
 *
 * Three steps in one screen:
 *  1. Select a lease (hidden if `lease` is given by the caller).
 *  2. Pick a date range (from month/year → to month/year) and a default
 *     received amount that pre-fills every row.
 *  3. Reviewable per-row checklist: each month shows the expected amount
 *     (from the rent_revision in effect for that month — never the
 *     current rent), the editable received amount, the computed status
 *     and outstanding balance, and a checkbox. The summary line below
 *     totals expected/received/outstanding for the checked rows.
 *
 * Months that already have a Payment record are listed but disabled and
 * not selectable, so the user can see why a known period was skipped.
 */
export default function BulkPaymentModal({ lease = null, leases = null, onClose, onSaved }) {
  const { year: curYear, month: curMonth } = currentYearMonth()
  const [selectedLeaseId, setSelectedLeaseId] = useState(lease ? lease.id : '')
  const [fromYear, setFromYear] = useState(curYear - 1)
  const [fromMonth, setFromMonth] = useState(1)
  const [toYear, setToYear] = useState(curYear)
  const [toMonth, setToMonth] = useState(curMonth)
  const [defaultReceived, setDefaultReceived] = useState('0')
  const [preview, setPreview] = useState(null) // { rows: [...] }
  const [rowState, setRowState] = useState({})  // keyed "YYYY-MM": { received, checked }
  const [defaultNotes, setDefaultNotes] = useState('Saisie rétroactive')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const fetchPreview = async () => {
    if (!selectedLeaseId) {
      toast.error('Sélectionnez un bail')
      return
    }
    setLoading(true)
    try {
      const r = await api.get('/payments/bulk/preview', {
        params: {
          lease_id: selectedLeaseId,
          from_year: fromYear, from_month: fromMonth,
          to_year: toYear, to_month: toMonth,
        },
      })
      setPreview(r.data)
      const init = {}
      for (const row of r.data.rows) {
        const k = `${row.year}-${row.month}`
        init[k] = {
          received: row.has_existing ? '0' : String(defaultReceived ?? 0),
          checked: !row.has_existing,
        }
      }
      setRowState(init)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    } finally {
      setLoading(false)
    }
  }

  // When the user changes the default received, re-apply it to every
  // row that's still selectable (preserving any explicit per-row edits
  // would surprise the user mid-flow — Step 3 in the spec applies the
  // default to all checked months).
  useEffect(() => {
    if (!preview) return
    const next = {}
    for (const row of preview.rows) {
      const k = `${row.year}-${row.month}`
      next[k] = row.has_existing
        ? { received: '0', checked: false }
        : { received: String(defaultReceived ?? 0), checked: rowState[k]?.checked ?? true }
    }
    setRowState(next)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultReceived])

  const setRow = (key, patch) => setRowState((s) => ({ ...s, [key]: { ...s[key], ...patch } }))

  const computed = useMemo(() => {
    if (!preview) return { rows: [], totalExpected: 0, totalReceived: 0, totalOutstanding: 0, checkedCount: 0 }
    const rows = preview.rows.map((row) => {
      const k = `${row.year}-${row.month}`
      const state = rowState[k] ?? { received: '0', checked: false }
      const expected = Number(row.expected_amount)
      const received = Number(state.received || 0)
      let status = 'unpaid'
      if (received >= expected && expected > 0) status = 'paid'
      else if (received > 0) status = 'partial'
      const outstanding = Math.max(expected - received, 0)
      return { ...row, key: k, expected, received, status, outstanding, checked: state.checked }
    })
    const checked = rows.filter((r) => r.checked && !r.has_existing)
    return {
      rows,
      totalExpected: checked.reduce((acc, r) => acc + r.expected, 0),
      totalReceived: checked.reduce((acc, r) => acc + r.received, 0),
      totalOutstanding: checked.reduce((acc, r) => acc + r.outstanding, 0),
      checkedCount: checked.length,
    }
  }, [preview, rowState])

  const submit = async () => {
    if (!preview) return
    const rows = computed.rows
      .filter((r) => r.checked && !r.has_existing)
      .map((r) => ({
        year: r.year, month: r.month,
        received_amount: r.received,
        notes: defaultNotes || null,
      }))
    if (rows.length === 0) {
      toast.error('Aucune période sélectionnée')
      return
    }
    setSaving(true)
    try {
      const r = await api.post('/payments/bulk', { lease_id: Number(selectedLeaseId), rows })
      toast.success(
        `${r.data.created_count} paiements créés — Solde total enregistré : ${fmtCurrency(r.data.total_outstanding)}`
      )
      onSaved()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const leaseLabel = (l) =>
    `${l.property?.name ?? `Bien #${l.property_id}`} — ${l.tenant?.last_name ?? ''} ${l.tenant?.first_name ?? ''}`

  const statusBadge = (s) => {
    if (s === 'paid')    return <span className="text-green-700 text-xs font-medium">Payé</span>
    if (s === 'partial') return <span className="text-orange-600 text-xs font-medium">Partiel</span>
    return <span className="text-red-600 text-xs font-medium">Impayé</span>
  }

  return (
    <Modal title="Saisie groupée de paiements" onClose={onClose}>
      <div className="space-y-4 max-h-[75vh] overflow-y-auto pr-1">
        {leases && (
          <div>
            <label className="form-label">Bail</label>
            <select
              className="form-input"
              value={selectedLeaseId}
              onChange={(e) => { setSelectedLeaseId(e.target.value); setPreview(null) }}
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
            <label className="form-label">De (mois / année)</label>
            <div className="flex gap-2">
              <select className="form-input" value={fromMonth} onChange={(e) => setFromMonth(Number(e.target.value))}>
                {MONTHS_FR.slice(1).map((m, i) => <option key={i + 1} value={i + 1}>{m}</option>)}
              </select>
              <input type="number" className="form-input w-24" value={fromYear}
                onChange={(e) => setFromYear(Number(e.target.value))} />
            </div>
          </div>
          <div>
            <label className="form-label">À (mois / année)</label>
            <div className="flex gap-2">
              <select className="form-input" value={toMonth} onChange={(e) => setToMonth(Number(e.target.value))}>
                {MONTHS_FR.slice(1).map((m, i) => <option key={i + 1} value={i + 1}>{m}</option>)}
              </select>
              <input type="number" className="form-input w-24" value={toYear}
                onChange={(e) => setToYear(Number(e.target.value))} />
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="form-label">Montant reçu par défaut (€)</label>
            <input type="number" step="0.01" className="form-input"
              value={defaultReceived} onChange={(e) => setDefaultReceived(e.target.value)} />
            <p className="text-xs text-gray-400 mt-1">Pré-rempli sur chaque ligne, modifiable individuellement.</p>
          </div>
          <div>
            <label className="form-label">Notes (s'applique à tous les paiements créés)</label>
            <input className="form-input" value={defaultNotes} onChange={(e) => setDefaultNotes(e.target.value)} />
          </div>
        </div>

        <div className="flex justify-end">
          <button type="button" className="btn-secondary" onClick={fetchPreview} disabled={loading}>
            {loading ? 'Calcul…' : 'Lister les mois'}
          </button>
        </div>

        {preview && (
          <>
            <div className="border border-gray-200 rounded overflow-hidden">
              <table className="min-w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-2 py-2 w-10"></th>
                    <th className="px-2 py-2 text-left">Période</th>
                    <th className="px-2 py-2 text-right">Attendu</th>
                    <th className="px-2 py-2 text-right">Reçu</th>
                    <th className="px-2 py-2 text-right">Solde dû</th>
                    <th className="px-2 py-2 text-center">Statut</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {computed.rows.length === 0 && (
                    <tr><td colSpan={6} className="text-center text-gray-400 py-4">Aucune période</td></tr>
                  )}
                  {computed.rows.map((row) => (
                    <tr key={row.key} className={row.has_existing ? 'bg-gray-50 text-gray-400' : ''}>
                      <td className="px-2 py-1">
                        <input
                          type="checkbox"
                          disabled={row.has_existing}
                          checked={row.checked}
                          onChange={(e) => setRow(row.key, { checked: e.target.checked })}
                        />
                      </td>
                      <td className="px-2 py-1 font-medium">
                        {MONTHS_FR[row.month]} {row.year}
                        {row.has_existing && <span className="ml-2 text-xs">(déjà saisi)</span>}
                      </td>
                      <td className="px-2 py-1 text-right">{fmtCurrency(row.expected)}</td>
                      <td className="px-2 py-1 text-right">
                        <input
                          type="number" step="0.01"
                          className="form-input py-1 w-24 text-right"
                          disabled={row.has_existing || !row.checked}
                          value={rowState[row.key]?.received ?? '0'}
                          onChange={(e) => setRow(row.key, { received: e.target.value })}
                        />
                      </td>
                      <td className="px-2 py-1 text-right">
                        {row.outstanding > 0
                          ? <span className="text-red-600 font-medium">{fmtCurrency(row.outstanding)}</span>
                          : <span className="text-green-600">{fmtCurrency(0)}</span>}
                      </td>
                      <td className="px-2 py-1 text-center">{statusBadge(row.status)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="bg-blue-50 border border-blue-200 rounded p-3 text-sm grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div><span className="text-gray-500">Sélectionnés</span><div className="font-semibold">{computed.checkedCount}</div></div>
              <div><span className="text-gray-500">Total attendu</span><div className="font-semibold">{fmtCurrency(computed.totalExpected)}</div></div>
              <div><span className="text-gray-500">Total reçu</span><div className="font-semibold">{fmtCurrency(computed.totalReceived)}</div></div>
              <div><span className="text-gray-500">Solde total</span><div className="font-semibold text-red-600">{fmtCurrency(computed.totalOutstanding)}</div></div>
            </div>
          </>
        )}

        <div className="flex justify-end gap-3 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Annuler</button>
          <button
            type="button"
            className="btn-primary"
            disabled={saving || !preview || computed.checkedCount === 0}
            onClick={submit}
          >
            {saving ? 'Création…' : `Créer les périodes sélectionnées (${computed.checkedCount})`}
          </button>
        </div>
      </div>
    </Modal>
  )
}
