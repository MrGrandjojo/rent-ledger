import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import api from '../api'
import { useAuth } from '../AuthContext'

export default function ChangePassword() {
  const { setUser } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ current_password: '', new_password: '', confirm: '' })
  const [loading, setLoading] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    if (form.new_password !== form.confirm) {
      toast.error('Les mots de passe ne correspondent pas')
      return
    }
    if (form.new_password.length < 6) {
      toast.error('Le mot de passe doit contenir au moins 6 caractères')
      return
    }
    setLoading(true)
    try {
      await api.put('/auth/change-password', {
        current_password: form.current_password,
        new_password: form.new_password,
      })
      const me = await api.get('/auth/me')
      setUser(me.data)
      toast.success('Mot de passe modifié avec succès')
      navigate('/dashboard')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur lors du changement de mot de passe')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 to-blue-900 px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="text-5xl mb-3">🔐</div>
          <h1 className="text-2xl font-bold text-white">Changement de mot de passe</h1>
          <p className="text-blue-300 mt-1 text-sm">Veuillez définir un nouveau mot de passe</p>
        </div>

        <form onSubmit={submit} className="bg-white rounded-2xl shadow-2xl p-8 space-y-4">
          <div>
            <label className="form-label">Mot de passe actuel</label>
            <input
              type="password"
              className="form-input"
              value={form.current_password}
              onChange={(e) => setForm({ ...form, current_password: e.target.value })}
              required
              autoFocus
            />
          </div>
          <div>
            <label className="form-label">Nouveau mot de passe</label>
            <input
              type="password"
              className="form-input"
              value={form.new_password}
              onChange={(e) => setForm({ ...form, new_password: e.target.value })}
              required
            />
          </div>
          <div>
            <label className="form-label">Confirmer le mot de passe</label>
            <input
              type="password"
              className="form-input"
              value={form.confirm}
              onChange={(e) => setForm({ ...form, confirm: e.target.value })}
              required
            />
          </div>
          <button type="submit" disabled={loading} className="btn-primary w-full justify-center mt-2">
            {loading ? 'Enregistrement…' : 'Enregistrer'}
          </button>
        </form>
      </div>
    </div>
  )
}
