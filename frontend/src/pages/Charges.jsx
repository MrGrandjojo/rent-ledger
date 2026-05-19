import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import api from '../api'
import Modal from '../components/Modal'
import { fmtCurrency } from '../utils'

const EMPTY = { lease_id: '', year: new Date().getFullYear() - 1, total_actual_charges: '', total_provisions_collected: '', notes: '' }

function ChargesForm({ value, onChange, leases, editing }) {
  const set = (k) => (e) => onChange({ ...value, [k]: e.target.value })
  return (
    <div className="space-y-4">
      {!editing && (
        <div>
          <label className="form-label">Bail</label>
          <select className="form-input" value={value.lease_id} onChange={set('lease_id')} required>
            <option value="">— Sélectionner —</option>
            {leases.map((l) => (
              <option key={l.id} value={l.id}>{l.property?.name} — {l.tenant?.last_name} ({l.id})</option>
            ))}
          </select>
        </div>
      )}
      <div>
        <label className="form-label">Année de régularisation</label>
        <input type="number" className="form-input" value={value.year} onChange={set('year')} required />
      </div>
      <div>
        <label className="form-label">Charges réelles payées (€)</label>
        <input type="number" step="0.01" className="form-input" value={value.total_actual_charges} onChange={set('total_actual_charges')} required />
      </div>
      <div>
        <label className="form-label">Provisions perçues sur l'année (€)</label>
        <input type="number" step="0.01" className="form-input" value={value.total_provisions_collected} onChange={set('total_provisions_collected')} required />
      </div>
      {value.total_actual_charges && value.total_provisions_collected && (
        <div className={`p-3 rounded-lg text-sm font-medium ${
          Number(value.total_actual_charges) - Number(value.total_provisions_collected) > 0
            ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'
        }`}>
          Solde prévu : {fmtCurrency(Number(value.total_actual_charges) - Number(value.total_provisions_collected))}
          {Number(value.total_actual_charges) - Number(value.total_provisions_collected) > 0
            ? ' (à percevoir du locataire)'
            : ' (à rembourser au locataire)'}
        </div>
      )}
      <div>
        <label className="form-label">Notes</label>
        <textarea className="form-input" rows={2} value={value.notes || ''} onChange={set('notes')} />
      </div>
    </div>
  )
}

export default function Charges() {
  const [charges, setCharges] = useState([])
  const [leases, setLeases] = useState([])
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)

  const load = async () => {
    const [c, l] = await Promise.all([api.get('/charges'), api.get('/leases')])
    setCharges(c.data); setLeases(l.data)
  }
  useEffect(() => { load() }, [])

  const leaseLabel = (id) => {
    const l = leases.find((x) => x.id === id)
    return l ? `${l.property?.name} — ${l.tenant?.last_name}` : `Bail #${id}`
  }

  const openCreate = () => { setForm({ ...EMPTY, lease_id: leases[0]?.id || '' }); setModal('create') }
  const openEdit = (c) => {
    setForm({ lease_id: c.lease_id, year: c.year, total_actual_charges: c.total_actual_charges, total_provisions_collected: c.total_provisions_collected, notes: c.notes || '' })
    setModal({ edit: c })
  }

  const save = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      if (modal === 'create') {
        await api.post('/charges', form)
        toast.success('Régularisation créée')
      } else {
        await api.put(`/charges/${modal.edit.id}`, {
          total_actual_charges: form.total_actual_charges,
          total_provisions_collected: form.total_provisions_collected,
          notes: form.notes,
        })
        toast.success('Régularisation mise à jour')
      }
      await load(); setModal(null)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const del = async (c) => {
    if (!confirm('Supprimer cette régularisation ?')) return
    try {
      await api.delete(`/charges/${c.id}`)
      toast.success('Supprimé')
      load()
    } catch { toast.error('Erreur') }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-800">Régularisation des charges</h1>
        <button className="btn-primary" onClick={openCreate}>+ Nouvelle régularisation</button>
      </div>

      <div className="card p-0 overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="table-th">Bail</th>
              <th className="table-th">Année</th>
              <th className="table-th">Charges réelles</th>
              <th className="table-th">Provisions perçues</th>
              <th className="table-th">Solde</th>
              <th className="table-th text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {charges.length === 0 && (
              <tr><td colSpan={6} className="table-td text-center text-gray-400 py-8">Aucune régularisation</td></tr>
            )}
            {charges.map((c) => (
              <tr key={c.id} className="hover:bg-gray-50">
                <td className="table-td text-sm">{leaseLabel(c.lease_id)}</td>
                <td className="table-td font-medium">{c.year}</td>
                <td className="table-td">{fmtCurrency(c.total_actual_charges)}</td>
                <td className="table-td">{fmtCurrency(c.total_provisions_collected)}</td>
                <td className="table-td">
                  <span className={`font-semibold ${Number(c.balance) > 0 ? 'text-red-600' : 'text-green-600'}`}>
                    {fmtCurrency(c.balance)}
                    {Number(c.balance) > 0 ? ' (locataire doit)' : ' (à rembourser)'}
                  </span>
                </td>
                <td className="table-td text-right space-x-2">
                  <button className="btn-secondary btn-sm" onClick={() => openEdit(c)}>Modifier</button>
                  <button className="btn-danger btn-sm" onClick={() => del(c)}>Supprimer</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modal && (
        <Modal title={modal === 'create' ? 'Nouvelle régularisation' : 'Modifier la régularisation'} onClose={() => setModal(null)}>
          <form onSubmit={save}>
            <ChargesForm value={form} onChange={setForm} leases={leases} editing={modal !== 'create'} />
            <div className="flex justify-end gap-3 pt-4">
              <button type="button" className="btn-secondary" onClick={() => setModal(null)}>Annuler</button>
              <button type="submit" disabled={saving} className="btn-primary">{saving ? 'Enregistrement…' : 'Enregistrer'}</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
