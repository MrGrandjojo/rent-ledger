import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import api from '../api'
import { useAuth } from '../AuthContext'
import Modal from '../components/Modal'

// ── Users tab ─────────────────────────────────────────────────────────────

const EMPTY_USER = { username: '', email: '', role: 'user', temporary_password: '' }
const ROLE_LABEL = { admin: 'Administrateur', supervisor: 'Superviseur', user: 'Utilisateur' }

function UsersTab() {
  const { user: me } = useAuth()
  const canPromoteAdmin = me?.role === 'admin'
  const [users, setUsers] = useState([])
  const [modal, setModal] = useState(null) // null | 'create' | {tempPwd: string, username: string}
  const [form, setForm] = useState(EMPTY_USER)
  const [saving, setSaving] = useState(false)
  const roleOptions = canPromoteAdmin
    ? ['admin', 'supervisor', 'user']
    : ['supervisor', 'user']

  const load = () => api.get('/admin/users').then((r) => setUsers(r.data))
  useEffect(() => { load() }, [])

  const create = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      await api.post('/admin/users', form)
      toast.success('Utilisateur créé')
      setModal(null)
      setForm(EMPTY_USER)
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const toggleActive = async (u) => {
    try {
      await api.put(`/admin/users/${u.id}`, { is_active: !u.is_active })
      toast.success(u.is_active ? 'Utilisateur désactivé' : 'Utilisateur réactivé')
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    }
  }

  const changeRole = async (u, role) => {
    try {
      await api.put(`/admin/users/${u.id}`, { role })
      toast.success('Rôle mis à jour')
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    }
  }

  const deleteUser = async (u) => {
    if (!confirm(`Supprimer définitivement l'utilisateur "${u.username}" ? Cette action est irréversible.`)) return
    try {
      await api.delete(`/admin/users/${u.id}`)
      toast.success('Utilisateur supprimé')
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    }
  }

  const resetPassword = async (u) => {
    if (!confirm(`Réinitialiser le mot de passe de "${u.username}" ?`)) return
    try {
      const r = await api.post(`/admin/users/${u.id}/reset-password`)
      setModal({ tempPwd: r.data.temporary_password, username: u.username })
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Utilisateurs</h2>
        <button className="btn-primary" onClick={() => { setForm(EMPTY_USER); setModal('create') }}>+ Créer un utilisateur</button>
      </div>

      <div className="card p-0 overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="table-th">Identifiant</th>
              <th className="table-th">Email</th>
              <th className="table-th">Rôle</th>
              <th className="table-th">Statut</th>
              <th className="table-th text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {users.length === 0 && (
              <tr><td colSpan={5} className="table-td text-center text-gray-400 py-8">Aucun utilisateur</td></tr>
            )}
            {users.map((u) => (
              <tr key={u.id} className="hover:bg-gray-50">
                <td className="table-td font-medium text-gray-900">{u.username}</td>
                <td className="table-td text-sm text-gray-500">{u.email || '—'}</td>
                <td className="table-td">
                  <select
                    className="form-input py-1"
                    value={u.role}
                    disabled={u.role === 'admin' && !canPromoteAdmin}
                    onChange={(e) => changeRole(u, e.target.value)}
                  >
                    {roleOptions.map((r) => (
                      <option key={r} value={r}>{ROLE_LABEL[r]}</option>
                    ))}
                    {u.role === 'admin' && !canPromoteAdmin && (
                      <option value="admin">Administrateur</option>
                    )}
                  </select>
                </td>
                <td className="table-td">
                  <span className={u.is_active ? 'text-green-700' : 'text-gray-400'}>
                    {u.is_active ? 'Actif' : 'Désactivé'}
                  </span>
                </td>
                <td className="table-td text-right space-x-2">
                  <button className="btn-secondary btn-sm" onClick={() => resetPassword(u)}>Réinit. MDP</button>
                  <button className="btn-secondary btn-sm" onClick={() => toggleActive(u)}>
                    {u.is_active ? 'Désactiver' : 'Réactiver'}
                  </button>
                  <button className="btn-danger btn-sm" onClick={() => deleteUser(u)}>Supprimer</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modal === 'create' && (
        <Modal title="Créer un utilisateur" onClose={() => setModal(null)}>
          <form onSubmit={create} className="space-y-4">
            <div>
              <label className="form-label">Identifiant</label>
              <input className="form-input" value={form.username} required
                onChange={(e) => setForm({ ...form, username: e.target.value })} />
            </div>
            <div>
              <label className="form-label">Email</label>
              <input type="email" className="form-input" value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </div>
            <div>
              <label className="form-label">Rôle</label>
              <select className="form-input" value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}>
                {roleOptions.map((r) => (
                  <option key={r} value={r}>{ROLE_LABEL[r]}</option>
                ))}
              </select>
              {!canPromoteAdmin && (
                <p className="text-xs text-gray-500 mt-1">
                  Un superviseur ne peut pas créer un administrateur.
                </p>
              )}
            </div>
            <div>
              <label className="form-label">Mot de passe temporaire</label>
              <input className="form-input" value={form.temporary_password} required minLength={6}
                onChange={(e) => setForm({ ...form, temporary_password: e.target.value })} />
              <p className="text-xs text-gray-500 mt-1">L'utilisateur devra le changer à la première connexion.</p>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button type="button" className="btn-secondary" onClick={() => setModal(null)}>Annuler</button>
              <button type="submit" disabled={saving} className="btn-primary">
                {saving ? 'Création…' : 'Créer'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {modal && typeof modal === 'object' && modal.tempPwd && (
        <Modal title="Mot de passe temporaire" onClose={() => setModal(null)}>
          <div className="space-y-3">
            <p className="text-sm text-gray-600">
              Mot de passe temporaire pour <strong>{modal.username}</strong> — communiquez-le en personne, il ne sera plus affiché.
            </p>
            <div className="font-mono text-lg bg-gray-100 p-3 rounded select-all">{modal.tempPwd}</div>
            <div className="flex justify-end pt-2">
              <button className="btn-primary" onClick={() => setModal(null)}>Compris</button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Groups tab ────────────────────────────────────────────────────────────

const EMPTY_GROUP = { name: '', description: '' }

function GroupsTab() {
  const [groups, setGroups] = useState([])
  const [allUsers, setAllUsers] = useState([])
  const [allProperties, setAllProperties] = useState([])
  const [modal, setModal] = useState(null) // null | 'create' | {edit: detail}
  const [form, setForm] = useState(EMPTY_GROUP)
  const [selectedUsers, setSelectedUsers] = useState([])
  const [selectedProps, setSelectedProps] = useState([])
  const [saving, setSaving] = useState(false)

  const load = async () => {
    const [g, u, p] = await Promise.all([
      api.get('/admin/groups'),
      api.get('/admin/users'),
      api.get('/properties'),
    ])
    setGroups(g.data); setAllUsers(u.data); setAllProperties(p.data)
  }
  useEffect(() => { load() }, [])

  const openCreate = () => {
    setForm(EMPTY_GROUP); setSelectedUsers([]); setSelectedProps([])
    setModal('create')
  }

  const openEdit = async (g) => {
    const detail = await api.get(`/admin/groups/${g.id}`)
    setForm({ name: detail.data.name, description: detail.data.description || '' })
    setSelectedUsers(detail.data.user_ids || [])
    setSelectedProps(detail.data.property_ids || [])
    setModal({ edit: detail.data })
  }

  const save = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      let groupId
      if (modal === 'create') {
        const r = await api.post('/admin/groups', form)
        groupId = r.data.id
        toast.success('Groupe créé')
      } else {
        await api.put(`/admin/groups/${modal.edit.id}`, form)
        groupId = modal.edit.id
        toast.success('Groupe mis à jour')
      }
      await api.put(`/admin/groups/${groupId}/users`, { user_ids: selectedUsers })
      await api.put(`/admin/groups/${groupId}/properties`, { property_ids: selectedProps })
      setModal(null)
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const del = async (g) => {
    if (!confirm(`Supprimer le groupe "${g.name}" ? Les utilisateurs et biens associés perdront cet accès.`)) return
    try {
      await api.delete(`/admin/groups/${g.id}`)
      toast.success('Groupe supprimé')
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    }
  }

  const toggle = (list, setList, id) => {
    setList(list.includes(id) ? list.filter((x) => x !== id) : [...list, id])
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Groupes</h2>
        <button className="btn-primary" onClick={openCreate}>+ Créer un groupe</button>
      </div>

      <div className="card p-0 overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="table-th">Nom</th>
              <th className="table-th">Description</th>
              <th className="table-th text-center">Membres</th>
              <th className="table-th text-center">Biens</th>
              <th className="table-th text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {groups.length === 0 && (
              <tr><td colSpan={5} className="table-td text-center text-gray-400 py-8">Aucun groupe</td></tr>
            )}
            {groups.map((g) => (
              <tr key={g.id} className="hover:bg-gray-50">
                <td className="table-td font-medium text-gray-900">{g.name}</td>
                <td className="table-td text-sm text-gray-500">{g.description || '—'}</td>
                <td className="table-td text-center">{g.member_count}</td>
                <td className="table-td text-center">{g.property_count}</td>
                <td className="table-td text-right space-x-2">
                  <button className="btn-secondary btn-sm" onClick={() => openEdit(g)}>Modifier</button>
                  <button className="btn-danger btn-sm" onClick={() => del(g)}>Supprimer</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modal && (
        <Modal title={modal === 'create' ? 'Créer un groupe' : `Modifier "${modal.edit.name}"`} onClose={() => setModal(null)}>
          <form onSubmit={save} className="space-y-4">
            <div>
              <label className="form-label">Nom</label>
              <input className="form-input" value={form.name} required
                onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <label className="form-label">Description</label>
              <textarea className="form-input" rows={2} value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </div>
            <div>
              <label className="form-label">Utilisateurs ({selectedUsers.length} sélectionné·s)</label>
              <div className="border border-gray-200 rounded max-h-40 overflow-y-auto p-2 space-y-1">
                {allUsers.length === 0 && <p className="text-sm text-gray-400">Aucun utilisateur</p>}
                {allUsers.map((u) => (
                  <label key={u.id} className="flex items-center gap-2 text-sm cursor-pointer">
                    <input type="checkbox" checked={selectedUsers.includes(u.id)}
                      onChange={() => toggle(selectedUsers, setSelectedUsers, u.id)} />
                    <span>{u.username} <span className="text-xs text-gray-400">({u.role})</span></span>
                  </label>
                ))}
              </div>
            </div>
            <div>
              <label className="form-label">Biens ({selectedProps.length} sélectionné·s)</label>
              <div className="border border-gray-200 rounded max-h-40 overflow-y-auto p-2 space-y-1">
                {allProperties.length === 0 && <p className="text-sm text-gray-400">Aucun bien</p>}
                {allProperties.map((p) => (
                  <label key={p.id} className="flex items-center gap-2 text-sm cursor-pointer">
                    <input type="checkbox" checked={selectedProps.includes(p.id)}
                      onChange={() => toggle(selectedProps, setSelectedProps, p.id)} />
                    <span>{p.name} <span className="text-xs text-gray-400">— {p.address_city}</span></span>
                  </label>
                ))}
              </div>
            </div>
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

// ── Page ──────────────────────────────────────────────────────────────────

export default function Administration() {
  const [tab, setTab] = useState('users')
  const tabClass = (key) =>
    `px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
      tab === key
        ? 'border-blue-600 text-blue-600'
        : 'border-transparent text-gray-500 hover:text-gray-700'
    }`

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-800">Administration</h1>
      <div className="border-b border-gray-200 flex gap-2">
        <button className={tabClass('users')}  onClick={() => setTab('users')}>Utilisateurs</button>
        <button className={tabClass('groups')} onClick={() => setTab('groups')}>Groupes</button>
      </div>
      {tab === 'users'  && <UsersTab />}
      {tab === 'groups' && <GroupsTab />}
    </div>
  )
}
