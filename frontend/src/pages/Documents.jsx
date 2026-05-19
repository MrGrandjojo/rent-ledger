import { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import api from '../api'
import Modal from '../components/Modal'
import { fmtDatetime, docTypeLabel } from '../utils'

export default function Documents() {
  const [documents, setDocuments] = useState([])
  const [leases, setLeases] = useState([])
  const [leaseFilter, setLeaseFilter] = useState('')
  const [modal, setModal] = useState(false)
  const [uploadForm, setUploadForm] = useState({ lease_id: '', doc_type: 'other' })
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef()

  const load = async () => {
    const [d, l] = await Promise.all([api.get('/documents'), api.get('/leases')])
    setDocuments(d.data); setLeases(l.data)
  }
  useEffect(() => { load() }, [])

  const leaseLabel = (id) => {
    const l = leases.find((x) => x.id === id)
    return l ? `${l.property?.name} — ${l.tenant?.last_name}` : `Bail #${id}`
  }

  const filtered = leaseFilter
    ? documents.filter((d) => String(d.lease_id) === leaseFilter)
    : documents

  const upload = async (e) => {
    e.preventDefault()
    if (!file) { toast.error('Sélectionnez un fichier'); return }
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append('lease_id', uploadForm.lease_id)
      fd.append('doc_type', uploadForm.doc_type)
      fd.append('file', file)
      await api.post('/documents', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      toast.success('Document téléversé')
      await load()
      setModal(false)
      setFile(null)
      if (fileRef.current) fileRef.current.value = ''
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erreur')
    } finally {
      setUploading(false)
    }
  }

  const del = async (d) => {
    if (!confirm(`Supprimer "${d.file_name}" ?`)) return
    try {
      await api.delete(`/documents/${d.id}`)
      toast.success('Document supprimé')
      load()
    } catch { toast.error('Erreur') }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-gray-800">Documents</h1>
        <div className="flex items-center gap-3">
          <select className="form-input w-56" value={leaseFilter} onChange={(e) => setLeaseFilter(e.target.value)}>
            <option value="">Tous les baux</option>
            {leases.map((l) => (
              <option key={l.id} value={l.id}>{l.property?.name} — {l.tenant?.last_name}</option>
            ))}
          </select>
          <button className="btn-primary" onClick={() => { setUploadForm({ lease_id: leases[0]?.id || '', doc_type: 'other' }); setModal(true) }}>
            ⬆️ Téléverser
          </button>
        </div>
      </div>

      <div className="card p-0 overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="table-th">Fichier</th>
              <th className="table-th">Type</th>
              <th className="table-th">Bail</th>
              <th className="table-th">Date</th>
              <th className="table-th text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.length === 0 && (
              <tr><td colSpan={5} className="table-td text-center text-gray-400 py-8">Aucun document</td></tr>
            )}
            {filtered.map((d) => (
              <tr key={d.id} className="hover:bg-gray-50">
                <td className="table-td font-medium text-gray-900">{d.file_name}</td>
                <td className="table-td text-sm">{docTypeLabel(d.type)}</td>
                <td className="table-td text-sm text-gray-500">{leaseLabel(d.lease_id)}</td>
                <td className="table-td text-sm text-gray-500">{fmtDatetime(d.upload_date)}</td>
                <td className="table-td text-right space-x-2">
                  <a href={`/rental/api/documents/${d.id}/download`} target="_blank" rel="noreferrer" className="btn-secondary btn-sm">⬇️</a>
                  <button className="btn-danger btn-sm" onClick={() => del(d)}>🗑</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modal && (
        <Modal title="Téléverser un document" onClose={() => setModal(false)}>
          <form onSubmit={upload} className="space-y-4">
            <div>
              <label className="form-label">Bail</label>
              <select className="form-input" value={uploadForm.lease_id}
                onChange={(e) => setUploadForm({ ...uploadForm, lease_id: e.target.value })} required>
                <option value="">— Sélectionner —</option>
                {leases.map((l) => (
                  <option key={l.id} value={l.id}>{l.property?.name} — {l.tenant?.last_name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="form-label">Type de document</label>
              <select className="form-input" value={uploadForm.doc_type}
                onChange={(e) => setUploadForm({ ...uploadForm, doc_type: e.target.value })}>
                <option value="lease_scan">Scan du bail</option>
                <option value="rent_receipt">Quittance de loyer</option>
                <option value="other">Autre</option>
              </select>
            </div>
            <div>
              <label className="form-label">Fichier</label>
              <input ref={fileRef} type="file" className="form-input" onChange={(e) => setFile(e.target.files[0])} required />
            </div>
            <div className="flex justify-end gap-3">
              <button type="button" className="btn-secondary" onClick={() => setModal(false)}>Annuler</button>
              <button type="submit" disabled={uploading} className="btn-primary">{uploading ? 'Envoi…' : 'Téléverser'}</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
