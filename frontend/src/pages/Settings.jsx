import { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import api from '../api'

const MAX_SIGNATURE_BYTES = 500 * 1024

export default function Settings() {
  const [profile, setProfile] = useState(null)
  const [pwdForm, setPwdForm] = useState({ current_password: '', new_password: '', confirm: '' })
  const [savingProfile, setSavingProfile] = useState(false)
  const [savingPwd, setSavingPwd] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [previewCacheKey, setPreviewCacheKey] = useState(Date.now())
  const fileInputRef = useRef(null)

  const loadProfile = () => api.get('/profile').then((r) => setProfile(r.data))
  useEffect(() => { loadProfile() }, [])

  const setField = (k) => (e) => setProfile({ ...profile, [k]: e.target.value })

  const saveProfile = async (e) => {
    e.preventDefault()
    setSavingProfile(true)
    try {
      await api.put('/profile', {
        landlord_name: profile.landlord_name || '',
        landlord_address: profile.landlord_address || '',
        landlord_phone: profile.landlord_phone || '',
        landlord_email: profile.landlord_email || '',
      })
      toast.success('Profil enregistré')
    } catch {
      toast.error('Erreur lors de la sauvegarde')
    } finally {
      setSavingProfile(false)
    }
  }

  const changePassword = async (e) => {
    e.preventDefault()
    if (pwdForm.new_password !== pwdForm.confirm) {
      toast.error('Les mots de passe ne correspondent pas'); return
    }
    setSavingPwd(true)
    try {
      await api.put('/auth/change-password', {
        current_password: pwdForm.current_password,
        new_password: pwdForm.new_password,
      })
      toast.success('Mot de passe modifié')
      setPwdForm({ current_password: '', new_password: '', confirm: '' })
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    } finally {
      setSavingPwd(false)
    }
  }

  const onPickFile = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!['image/png', 'image/jpeg'].includes(file.type)) {
      toast.error('PNG ou JPG uniquement')
      e.target.value = ''
      return
    }
    if (file.size > MAX_SIGNATURE_BYTES) {
      toast.error('Fichier trop volumineux (500 KB max)')
      e.target.value = ''
      return
    }
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const r = await api.post('/profile/signature', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setProfile(r.data)
      setPreviewCacheKey(Date.now())
      toast.success('Signature enregistrée')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const deleteSignature = async () => {
    if (!confirm('Supprimer la signature enregistrée ?')) return
    try {
      await api.delete('/profile/signature')
      const r = await api.get('/profile')
      setProfile(r.data)
      toast.success('Signature supprimée')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    }
  }

  if (!profile) return <p className="text-gray-400">Chargement…</p>

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-800">Paramètres</h1>

      {/* Landlord info */}
      <div className="card">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Informations du bailleur</h2>
        <p className="text-sm text-gray-500 mb-4">Ces informations apparaissent sur les quittances de loyer (PDF).</p>
        <form onSubmit={saveProfile} className="space-y-4">
          <div>
            <label className="form-label">Nom complet</label>
            <input className="form-input" value={profile.landlord_name || ''} onChange={setField('landlord_name')} />
          </div>
          <div>
            <label className="form-label">Adresse</label>
            <textarea className="form-input" rows={3} value={profile.landlord_address || ''} onChange={setField('landlord_address')} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="form-label">Téléphone</label>
              <input className="form-input" value={profile.landlord_phone || ''} onChange={setField('landlord_phone')} />
            </div>
            <div>
              <label className="form-label">Email</label>
              <input type="email" className="form-input" value={profile.landlord_email || ''} onChange={setField('landlord_email')} />
            </div>
          </div>
          <div className="flex justify-end">
            <button type="submit" disabled={savingProfile} className="btn-primary">
              {savingProfile ? 'Enregistrement…' : 'Enregistrer'}
            </button>
          </div>
        </form>
      </div>

      {/* Signature */}
      <div className="card">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Signature</h2>
        <p className="text-sm text-gray-500 mb-4">
          Image PNG ou JPG, 500 KB maximum. Stockée chiffrée (AES-256-GCM) — l'aperçu est volontairement flou.
        </p>

        {profile.has_signature && (
          <div className="mb-4">
            <p className="text-sm text-gray-600 mb-2">Aperçu (flouté)</p>
            <img
              src={`/rental/api/profile/signature/preview?t=${previewCacheKey}`}
              alt="Aperçu de la signature"
              className="border border-gray-200 rounded bg-white max-h-24"
            />
          </div>
        )}

        <div className="flex items-center gap-3">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg"
            onChange={onPickFile}
            disabled={uploading}
            className="text-sm"
          />
          {profile.has_signature && (
            <button type="button" className="btn-danger btn-sm" onClick={deleteSignature}>
              Supprimer la signature
            </button>
          )}
        </div>
      </div>

      {/* Change password */}
      <div className="card">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Changer le mot de passe</h2>
        <form onSubmit={changePassword} className="space-y-4">
          <div>
            <label className="form-label">Mot de passe actuel</label>
            <input type="password" className="form-input" value={pwdForm.current_password}
              onChange={(e) => setPwdForm({ ...pwdForm, current_password: e.target.value })} required />
          </div>
          <div>
            <label className="form-label">Nouveau mot de passe</label>
            <input type="password" className="form-input" value={pwdForm.new_password}
              onChange={(e) => setPwdForm({ ...pwdForm, new_password: e.target.value })} required />
          </div>
          <div>
            <label className="form-label">Confirmer</label>
            <input type="password" className="form-input" value={pwdForm.confirm}
              onChange={(e) => setPwdForm({ ...pwdForm, confirm: e.target.value })} required />
          </div>
          <div className="flex justify-end">
            <button type="submit" disabled={savingPwd} className="btn-primary">
              {savingPwd ? 'Modification…' : 'Changer le mot de passe'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
