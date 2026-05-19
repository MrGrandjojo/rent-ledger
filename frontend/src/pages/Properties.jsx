import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import api from '../api'
import Modal from '../components/Modal'
import { propertyTypeLabel } from '../utils'

const EMPTY = { name: '', type: 'apartment', address_street: '', address_city: '', address_zip: '', address_country: 'France' }

function PropertyForm({ value, onChange }) {
  const set = (k) => (e) => onChange({ ...value, [k]: e.target.value })
  return (
    <div className="space-y-4">
      <div>
        <label className="form-label">Nom du bien</label>
        <input className="form-input" value={value.name} onChange={set('name')} required />
      </div>
      <div>
        <label className="form-label">Type</label>
        <select className="form-input" value={value.type} onChange={set('type')}>
          <option value="apartment">Appartement</option>
          <option value="parking">Parking</option>
        </select>
      </div>
      <div>
        <label className="form-label">Adresse</label>
        <input className="form-input" placeholder="Rue" value={value.address_street} onChange={set('address_street')} required />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="form-label">Code postal</label>
          <input className="form-input" value={value.address_zip} onChange={set('address_zip')} required />
        </div>
        <div className="col-span-2">
          <label className="form-label">Ville</label>
          <input className="form-input" value={value.address_city} onChange={set('address_city')} required />
        </div>
      </div>
      <div>
        <label className="form-label">Pays</label>
        <input className="form-input" value={value.address_country} onChange={set('address_country')} />
      </div>
    </div>
  )
}

export default function Properties() {
  const [properties, setProperties] = useState([])
  const [modal, setModal] = useState(null) // null | 'create' | {edit: property}
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)

  const load = () => api.get('/properties').then((r) => setProperties(r.data))
  useEffect(() => { load() }, [])

  const openCreate = () => { setForm(EMPTY); setModal('create') }
  const openEdit = (p) => { setForm({ ...p }); setModal({ edit: p }) }
  const closeModal = () => setModal(null)

  const save = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      if (modal === 'create') {
        await api.post('/properties', form)
        toast.success('Bien créé')
      } else {
        await api.put(`/properties/${modal.edit.id}`, form)
        toast.success('Bien mis à jour')
      }
      await load()
      closeModal()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const del = async (p) => {
    if (!confirm(`Supprimer le bien "${p.name}" ?`)) return
    try {
      await api.delete(`/properties/${p.id}`)
      toast.success('Bien supprimé')
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Impossible de supprimer')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-800">Biens immobiliers</h1>
        <button className="btn-primary" onClick={openCreate}>+ Ajouter un bien</button>
      </div>

      <div className="card p-0 overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="table-th">Nom</th>
              <th className="table-th">Type</th>
              <th className="table-th">Adresse</th>
              <th className="table-th text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {properties.length === 0 && (
              <tr><td colSpan={4} className="table-td text-center text-gray-400 py-8">Aucun bien enregistré</td></tr>
            )}
            {properties.map((p) => (
              <tr key={p.id} className="hover:bg-gray-50">
                <td className="table-td font-medium text-gray-900">{p.name}</td>
                <td className="table-td">{propertyTypeLabel(p.type)}</td>
                <td className="table-td text-sm text-gray-500">
                  {p.address_street}, {p.address_zip} {p.address_city}
                </td>
                <td className="table-td text-right space-x-2">
                  <button className="btn-secondary btn-sm" onClick={() => openEdit(p)}>Modifier</button>
                  <button className="btn-danger btn-sm" onClick={() => del(p)}>Supprimer</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modal && (
        <Modal title={modal === 'create' ? 'Ajouter un bien' : 'Modifier le bien'} onClose={closeModal}>
          <form onSubmit={save} className="space-y-4">
            <PropertyForm value={form} onChange={setForm} />
            <div className="flex justify-end gap-3 pt-2">
              <button type="button" className="btn-secondary" onClick={closeModal}>Annuler</button>
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
