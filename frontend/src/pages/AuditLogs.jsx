import { Fragment, useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import api from '../api'
import Modal from '../components/Modal'
import { fmtDatetime } from '../utils'

const ACTION_LABELS = {
  create: { label: 'Création',    cls: 'bg-green-100 text-green-800' },
  update: { label: 'Modification', cls: 'bg-blue-100 text-blue-800' },
  delete: { label: 'Suppression', cls: 'bg-red-100 text-red-800' },
  export: { label: 'Export',      cls: 'bg-purple-100 text-purple-800' },
}

const ENTITY_LABELS = {
  property: 'Bien',
  lease: 'Bail',
  tenant: 'Locataire',
  payment: 'Paiement',
  rent_revision: 'Révision de loyer',
  charge_regularization: 'Régularisation',
  document: 'Document',
  user: 'Utilisateur',
  group: 'Groupe',
  audit_log: 'Journal',
}

function ActionBadge({ action }) {
  const cfg = ACTION_LABELS[action] ?? { label: action, cls: 'bg-gray-100 text-gray-800' }
  return <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${cfg.cls}`}>{cfg.label}</span>
}

function DetailBlock({ title, data }) {
  if (!data) return null
  return (
    <div className="text-xs">
      <div className="text-gray-500 font-semibold mb-1">{title}</div>
      <pre className="bg-gray-50 border border-gray-200 rounded p-2 overflow-x-auto">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  )
}

export default function AuditLogs() {
  const [logs, setLogs] = useState([])
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState({
    start: '', end: '', user_id: '', entity_type: '', action: '',
  })
  const [expanded, setExpanded] = useState(() => new Set())
  const [showConfirm, setShowConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const params = {}
      if (filters.start) params.start = `${filters.start}T00:00:00`
      if (filters.end)   params.end   = `${filters.end}T23:59:59`
      if (filters.user_id)     params.user_id = Number(filters.user_id)
      if (filters.entity_type) params.entity_type = filters.entity_type
      if (filters.action)      params.action = filters.action
      const r = await api.get('/audit-logs', { params })
      setLogs(r.data)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur de chargement')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { api.get('/admin/users').then((r) => setUsers(r.data)).catch(() => {}) }, [])
  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const toggleRow = (id) => {
    const next = new Set(expanded)
    if (next.has(id)) next.delete(id); else next.add(id)
    setExpanded(next)
  }

  const exportCsv = async () => {
    try {
      const params = {}
      if (filters.start) params.start = `${filters.start}T00:00:00`
      if (filters.end)   params.end   = `${filters.end}T23:59:59`
      if (filters.user_id)     params.user_id = Number(filters.user_id)
      if (filters.entity_type) params.entity_type = filters.entity_type
      if (filters.action)      params.action = filters.action
      const r = await api.get('/audit-logs/export', { params, responseType: 'blob' })
      const url = URL.createObjectURL(r.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `audit_logs_${new Date().toISOString().slice(0, 10)}.csv`
      a.click()
      URL.revokeObjectURL(url)
      toast.success('Export téléchargé')
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || "Échec de l'export")
    }
  }

  const deleteAll = async () => {
    setDeleting(true)
    try {
      const r = await api.delete('/audit-logs')
      toast.success(`${r.data.deleted} entrée(s) supprimée(s)`)
      setShowConfirm(false)
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    } finally {
      setDeleting(false)
    }
  }

  const userLabel = useMemo(() => (id) => {
    const u = users.find((x) => x.id === id)
    return u ? u.username : `#${id ?? '—'}`
  }, [users])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-gray-800">Journaux</h1>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={exportCsv}>Exporter (CSV)</button>
          <button className="btn-danger" onClick={() => setShowConfirm(true)}>Supprimer les logs</button>
        </div>
      </div>

      <div className="card">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          <div>
            <label className="form-label">Du</label>
            <input type="date" className="form-input" value={filters.start}
              onChange={(e) => setFilters({ ...filters, start: e.target.value })} />
          </div>
          <div>
            <label className="form-label">Au</label>
            <input type="date" className="form-input" value={filters.end}
              onChange={(e) => setFilters({ ...filters, end: e.target.value })} />
          </div>
          <div>
            <label className="form-label">Utilisateur</label>
            <select className="form-input" value={filters.user_id}
              onChange={(e) => setFilters({ ...filters, user_id: e.target.value })}>
              <option value="">Tous</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
            </select>
          </div>
          <div>
            <label className="form-label">Entité</label>
            <select className="form-input" value={filters.entity_type}
              onChange={(e) => setFilters({ ...filters, entity_type: e.target.value })}>
              <option value="">Toutes</option>
              {Object.entries(ENTITY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div>
            <label className="form-label">Action</label>
            <select className="form-input" value={filters.action}
              onChange={(e) => setFilters({ ...filters, action: e.target.value })}>
              <option value="">Toutes</option>
              {Object.entries(ACTION_LABELS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>
        </div>
        <div className="flex justify-end mt-3">
          <button className="btn-primary btn-sm" onClick={load}>Appliquer les filtres</button>
        </div>
      </div>

      <div className="card p-0 overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="table-th w-44">Date / heure</th>
              <th className="table-th">Utilisateur</th>
              <th className="table-th">Action</th>
              <th className="table-th">Entité</th>
              <th className="table-th">Libellé</th>
              <th className="table-th text-right">Détail</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading && (
              <tr><td colSpan={6} className="table-td text-center text-gray-400 py-8">Chargement…</td></tr>
            )}
            {!loading && logs.length === 0 && (
              <tr><td colSpan={6} className="table-td text-center text-gray-400 py-8">Aucune entrée</td></tr>
            )}
            {!loading && logs.map((l) => (
              <Fragment key={l.id}>
                <tr className="hover:bg-gray-50">
                  <td className="table-td text-sm whitespace-nowrap">{fmtDatetime(l.created_at)}</td>
                  <td className="table-td text-sm">{l.user_display_name || userLabel(l.user_id)}</td>
                  <td className="table-td"><ActionBadge action={l.action} /></td>
                  <td className="table-td text-sm">{ENTITY_LABELS[l.entity_type] ?? l.entity_type}</td>
                  <td className="table-td text-sm">{l.entity_label || '—'}</td>
                  <td className="table-td text-right">
                    <button className="btn-secondary btn-sm" onClick={() => toggleRow(l.id)}>
                      {expanded.has(l.id) ? '▲' : '▼'}
                    </button>
                  </td>
                </tr>
                {expanded.has(l.id) && (
                  <tr className="bg-gray-50">
                    <td colSpan={6} className="px-4 py-3 space-y-3">
                      <div className="text-xs text-gray-500">
                        ID #{l.id} · entity_id={l.entity_id || '—'} · ip={l.ip_address || '—'}
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <DetailBlock title="Avant" data={l.before} />
                        <DetailBlock title="Après" data={l.after} />
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {showConfirm && (
        <Modal title="Supprimer tous les journaux ?" onClose={() => setShowConfirm(false)}>
          <div className="space-y-3">
            <p className="text-sm text-gray-700">
              Cette action est irréversible. Toutes les entrées d'audit seront supprimées.
              La suppression elle-même générera une nouvelle entrée de journal.
            </p>
            <div className="flex justify-end gap-3 pt-2">
              <button className="btn-secondary" onClick={() => setShowConfirm(false)}>Annuler</button>
              <button className="btn-danger" disabled={deleting} onClick={deleteAll}>
                {deleting ? 'Suppression…' : 'Supprimer définitivement'}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
