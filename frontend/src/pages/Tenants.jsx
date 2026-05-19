import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import api from '../api'
import Modal from '../components/Modal'

const EMPTY = { first_name: '', last_name: '', email: '', phone: '', guarantor_name: '' }

function TenantForm({ value, onChange }) {
  const set = (k) => (e) => onChange({ ...value, [k]: e.target.value })
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="form-label">Prénom</label>
          <input className="form-input" value={value.first_name} onChange={set('first_name')} required />
        </div>
        <div>
          <label className="form-label">Nom</label>
          <input className="form-input" value={value.last_name} onChange={set('last_name')} required />
        </div>
      </div>
      <div>
        <label className="form-label">Email</label>
        <input type="email" className="form-input" value={value.email || ''} onChange={set('email')} />
      </div>
      <div>
        <label className="form-label">Téléphone</label>
        <input className="form-input" value={value.phone || ''} onChange={set('phone')} />
      </div>
      <div>
        <label className="form-label">Garant (nom complet)</label>
        <input className="form-input" value={value.guarantor_name || ''} onChange={set('guarantor_name')} placeholder="Optionnel" />
      </div>
    </div>
  )
}

export default function Tenants() {
  const [tenants, setTenants] = useState([])
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)

  const load = () => api.get('/tenants').then((r) => setTenants(r.data))
  useEffect(() => { load() }, [])

  const openCreate = () => { setForm(EMPTY); setModal('create') }
  const openEdit = (t) => { setForm({ ...t }); setModal({ edit: t }) }

  const save = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      if (modal === 'create') {
        await api.post('/tenants', form)
        toast.success('Locataire créé')
      } else {
        await api.put(`/tenants/${modal.edit.id}`, form)
        toast.success('Locataire mis à jour')
      }
      await load()
      setModal(null)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const del = async (t) => {
    if (!confirm(`Supprimer le locataire "${t.first_name} ${t.last_name}" ?`)) return
    try {
      await api.delete(`/tenants/${t.id}`)
      toast.success('Locataire supprimé')
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Impossible de supprimer')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-800">Locataires</h1>
        <button className="btn-primary" onClick={openCreate}>+ Ajouter un locataire</button>
      </div>

      <div className="card p-0 overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="table-th">Nom</th>
              <th className="table-th">Contact</th>
              <th className="table-th">Garant</th>
              <th className="table-th text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {tenants.length === 0 && (
              <tr><td colSpan={4} className="table-td text-center text-gray-400 py-8">Aucun locataire enregistré</td></tr>
            )}
            {tenants.map((t) => (
              <tr key={t.id} className="hover:bg-gray-50">
                <td className="table-td font-medium text-gray-900">{t.last_name} {t.first_name}</td>
                <td className="table-td text-sm">
                  {t.email && <div>{t.email}</div>}
                  {t.phone && <div className="text-gray-500">{t.phone}</div>}
                </td>
                <td className="table-td text-sm text-gray-500">{t.guarantor_name || '—'}</td>
                <td className="table-td text-right space-x-2">
                  <button className="btn-secondary btn-sm" onClick={() => openEdit(t)}>Modifier</button>
                  <button className="btn-danger btn-sm" onClick={() => del(t)}>Supprimer</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modal && (
        <Modal title={modal === 'create' ? 'Ajouter un locataire' : 'Modifier le locataire'} onClose={() => setModal(null)}>
          <form onSubmit={save} className="space-y-4">
            <TenantForm value={form} onChange={setForm} />
            <div className="flex justify-end gap-3 pt-2">
              <button type="button" className="btn-secondary" onClick={() => setModal(null)}>Annuler</button>
              <button type="submit" disabled={saving} className="btn-primary">
                {saving ? 'Enregistrement…' : 'Enregistrer'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
