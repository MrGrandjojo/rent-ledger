import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import api from '../api'
import Modal from '../components/Modal'
import { fmtCurrency, fmtDate, leaseTypeLabel } from '../utils'

const EMPTY = {
  property_id: '', tenant_id: '',
  parent_lease_id: '',          // '' = bail principal
  lease_type: 'unfurnished',
  start_date: '',
  monthly_rent: '', monthly_charges: '0',
  security_deposit_amount: '', security_deposit_date: '',
  is_active: true,
}

function LeaseForm({ value, onChange, properties, tenants, leases, editingId }) {
  const set = (k) => (e) => {
    const v = e.target.type === 'checkbox' ? e.target.checked : e.target.value
    onChange({ ...value, [k]: v })
  }

  // Candidate parent leases on the same property, excluding self and existing amendments
  const candidateParents = useMemo(() => {
    if (!value.property_id) return []
    return leases.filter(
      (l) =>
        String(l.property_id) === String(value.property_id) &&
        l.parent_lease_id == null &&
        l.id !== editingId
    )
  }, [leases, value.property_id, editingId])

  const isAmendment = !!value.parent_lease_id
  const parent = isAmendment
    ? leases.find((l) => String(l.id) === String(value.parent_lease_id))
    : null

  // When amendment status toggles, reset lease_type to the parent's
  const setAmendmentToggle = (e) => {
    const v = e.target.value === 'yes'
    if (v) {
      const first = candidateParents[0]
      onChange({
        ...value,
        parent_lease_id: first ? String(first.id) : '',
        lease_type: first ? first.lease_type : value.lease_type,
      })
    } else {
      onChange({ ...value, parent_lease_id: '' })
    }
  }

  const setParent = (e) => {
    const id = e.target.value
    const p = leases.find((l) => String(l.id) === String(id))
    onChange({
      ...value,
      parent_lease_id: id,
      lease_type: p ? p.lease_type : value.lease_type,
    })
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="form-label">Bien</label>
          <select className="form-input" value={value.property_id} onChange={set('property_id')} required>
            <option value="">— Sélectionner —</option>
            {properties.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div>
          <label className="form-label">Locataire</label>
          <select className="form-input" value={value.tenant_id} onChange={set('tenant_id')} required>
            <option value="">— Sélectionner —</option>
            {tenants.map((t) => <option key={t.id} value={t.id}>{t.last_name} {t.first_name}</option>)}
          </select>
        </div>
      </div>

      <div>
        <label className="form-label">Avenant à un bail existant ?</label>
        <select
          className="form-input"
          value={isAmendment ? 'yes' : 'no'}
          onChange={setAmendmentToggle}
          disabled={!value.property_id}
        >
          <option value="no">Non, bail principal</option>
          <option value="yes" disabled={candidateParents.length === 0}>
            Oui, avenant {candidateParents.length === 0 ? '(aucun bail parent sur ce bien)' : ''}
          </option>
        </select>
      </div>

      {isAmendment && (
        <div>
          <label className="form-label">Bail parent</label>
          <select className="form-input" value={value.parent_lease_id} onChange={setParent} required>
            {candidateParents.map((l) => (
              <option key={l.id} value={l.id}>
                {l.tenant?.last_name} {l.tenant?.first_name} — début {fmtDate(l.start_date)}
              </option>
            ))}
          </select>
          {parent && (
            <p className="text-xs text-gray-500 mt-1">
              Type et date de fin hérités du bail parent : {leaseTypeLabel(parent.lease_type)}, fin {fmtDate(parent.end_date)}
            </p>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="form-label">Type de bail</label>
          <select
            className="form-input"
            value={value.lease_type}
            onChange={set('lease_type')}
            required
            disabled={isAmendment}
          >
            <option value="unfurnished">Non meublé (3 ans, préavis 6 mois)</option>
            <option value="furnished">Meublé (1 an, préavis 3 mois)</option>
            <option value="furnished_student">Meublé étudiant (9 mois, préavis 3 mois)</option>
          </select>
          {isAmendment && (
            <p className="text-xs text-gray-400 mt-1">Hérité du bail parent.</p>
          )}
        </div>
        <div>
          <label className="form-label">Date de début</label>
          <input type="date" className="form-input" value={value.start_date} onChange={set('start_date')} required />
          <p className="text-xs text-gray-400 mt-1">
            {isAmendment
              ? "La date de fin est héritée du bail parent."
              : "La date de fin est calculée automatiquement d'après le type de bail."}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="form-label">Loyer HC initial (€)</label>
          <input type="number" step="0.01" className="form-input" value={value.monthly_rent} onChange={set('monthly_rent')} required />
        </div>
        <div>
          <label className="form-label">Provision charges initiale (€)</label>
          <input type="number" step="0.01" className="form-input" value={value.monthly_charges} onChange={set('monthly_charges')} required />
        </div>
      </div>
      <p className="text-xs text-gray-400 -mt-2">
        Ces montants alimentent la révision "Initiale" dans l'historique des loyers.
        Toute modification ici les met à jour partout (tableau de bord, paiements, fiche du bail).
      </p>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="form-label">Dépôt de garantie (€)</label>
          <input type="number" step="0.01" className="form-input" value={value.security_deposit_amount || ''} onChange={set('security_deposit_amount')} />
        </div>
        <div>
          <label className="form-label">Date dépôt de garantie</label>
          <input type="date" className="form-input" value={value.security_deposit_date || ''} onChange={set('security_deposit_date')} />
        </div>
      </div>
      <div className="flex items-center gap-2">
        <input type="checkbox" id="is_active" checked={value.is_active} onChange={set('is_active')} className="rounded border-gray-300" />
        <label htmlFor="is_active" className="text-sm font-medium text-gray-700">
          Bail actif (décocher uniquement en cas de résiliation anticipée)
        </label>
      </div>
    </div>
  )
}

export default function Leases() {
  const [leases, setLeases] = useState([])
  const [properties, setProperties] = useState([])
  const [tenants, setTenants] = useState([])
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)

  const load = async () => {
    const [l, p, t] = await Promise.all([
      api.get('/leases'), api.get('/properties'), api.get('/tenants'),
    ])
    setLeases(l.data); setProperties(p.data); setTenants(t.data)
  }
  useEffect(() => { load() }, [])

  const openCreate = () => {
    setForm({ ...EMPTY, property_id: properties[0]?.id || '', tenant_id: tenants[0]?.id || '' })
    setModal('create')
  }
  const openEdit = (l) => {
    setForm({
      property_id: l.property_id, tenant_id: l.tenant_id,
      parent_lease_id: l.parent_lease_id ? String(l.parent_lease_id) : '',
      lease_type: l.lease_type || 'unfurnished',
      start_date: l.start_date || '',
      monthly_rent: l.initial_monthly_rent ?? '',
      monthly_charges: l.initial_monthly_charges ?? '',
      security_deposit_amount: l.security_deposit_amount || '',
      security_deposit_date: l.security_deposit_date || '',
      is_active: l.is_active,
    })
    setModal({ edit: l })
  }

  const save = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      const payload = { ...form }
      ;['security_deposit_date', 'security_deposit_amount'].forEach((k) => {
        if (!payload[k]) payload[k] = null
      })
      payload.parent_lease_id = payload.parent_lease_id ? Number(payload.parent_lease_id) : null
      if (modal === 'create') {
        await api.post('/leases', payload)
        toast.success('Bail créé')
      } else {
        await api.put(`/leases/${modal.edit.id}`, payload)
        toast.success('Bail mis à jour')
      }
      await load()
      setModal(null)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const del = async (l) => {
    if (!confirm('Supprimer ce bail ?')) return
    try {
      await api.delete(`/leases/${l.id}`)
      toast.success('Bail supprimé')
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Impossible de supprimer')
    }
  }

  const editingId = modal && modal.edit ? modal.edit.id : null

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-800">Baux</h1>
        <button className="btn-primary" onClick={openCreate}>+ Nouveau bail</button>
      </div>

      <div className="card p-0 overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="table-th">Bien</th>
              <th className="table-th">Locataire</th>
              <th className="table-th">Type</th>
              <th className="table-th">Période</th>
              <th className="table-th">Loyer CC (initial)</th>
              <th className="table-th">Loyer CC actuel</th>
              <th className="table-th">Statut</th>
              <th className="table-th text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {leases.length === 0 && (
              <tr><td colSpan={8} className="table-td text-center text-gray-400 py-8">Aucun bail enregistré</td></tr>
            )}
            {leases.map((l) => (
              <tr key={l.id} className="hover:bg-gray-50">
                <td className="table-td">
                  <span className="font-medium text-gray-900">{l.property?.name}</span>
                  {l.parent_lease_id && (
                    <span className="ml-2 text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full">Avenant</span>
                  )}
                </td>
                <td className="table-td">{l.tenant?.last_name} {l.tenant?.first_name}</td>
                <td className="table-td text-sm">{leaseTypeLabel(l.lease_type)}</td>
                <td className="table-td text-sm text-gray-500">
                  {fmtDate(l.start_date)} → {fmtDate(l.end_date)}
                </td>
                <td className="table-td">
                  {l.initial_monthly_total != null ? fmtCurrency(l.initial_monthly_total) : '—'}
                </td>
                <td className="table-td font-medium">
                  {l.current_monthly_total != null ? fmtCurrency(l.current_monthly_total) : '—'}
                </td>
                <td className="table-td">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${l.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                    {l.is_active ? 'Actif' : 'Terminé'}
                  </span>
                </td>
                <td className="table-td text-right space-x-2">
                  <Link to={`/leases/${l.id}`} className="btn-secondary btn-sm">Détail</Link>
                  <button className="btn-secondary btn-sm" onClick={() => openEdit(l)}>Modifier</button>
                  <button className="btn-danger btn-sm" onClick={() => del(l)}>Supprimer</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modal && (
        <Modal title={modal === 'create' ? 'Nouveau bail' : 'Modifier le bail'} onClose={() => setModal(null)}>
          <form onSubmit={save}>
            <LeaseForm
              value={form} onChange={setForm}
              properties={properties} tenants={tenants}
              leases={leases} editingId={editingId}
            />
            <div className="flex justify-end gap-3 pt-4">
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
