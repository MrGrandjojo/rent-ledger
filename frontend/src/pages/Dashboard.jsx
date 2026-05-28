import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'
import StatusBadge from '../components/StatusBadge'
import { fmtCurrency, propertyTypeLabel, MONTHS_FR } from '../utils'

function StatCard({ label, value, sub, color = 'blue' }) {
  const colors = {
    blue:   'border-blue-500 bg-blue-50',
    green:  'border-green-500 bg-green-50',
    orange: 'border-orange-500 bg-orange-50',
    red:    'border-red-500 bg-red-50',
  }
  return (
    <div className={`bg-white rounded-lg shadow-sm border border-gray-200 border-t-4 px-4 py-3 ${colors[color]}`}>
      <p className="text-sm text-gray-500 leading-tight">{label}</p>
      <p className="text-2xl font-bold text-gray-800 leading-tight mt-1">{value}</p>
      {sub && <p className="text-xs text-gray-500 leading-tight mt-0.5">{sub}</p>}
    </div>
  )
}

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/dashboard').then((r) => { setData(r.data); setLoading(false) })
  }, [])

  if (loading) return <p className="text-gray-400">Chargement…</p>

  const now = new Date()
  const periodLabel = `${MONTHS_FR[now.getMonth() + 1]} ${now.getFullYear()}`

  const { stats, rows } = data

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-800">Tableau de bord</h1>
      <p className="text-sm text-gray-500">Période en cours : {periodLabel}</p>

      {(Number(stats.cdp_alerts_count) > 0 || Number(stats.cdp_expired_unpaid_count) > 0) && (
        <Link
          to="/procedures"
          className="block rounded-lg border-l-4 border-orange-500 bg-orange-50 px-4 py-3 hover:bg-orange-100"
        >
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <p className="text-sm font-semibold text-orange-900">
                ⚖️ Procédures à surveiller
              </p>
              <p className="text-xs text-orange-800 mt-0.5">
                {Number(stats.cdp_alerts_count) > 0 && (
                  <>
                    {stats.cdp_alerts_count} commandement{stats.cdp_alerts_count > 1 ? 's' : ''} de payer
                    {' '}arrive{stats.cdp_alerts_count > 1 ? 'nt' : ''} à échéance dans 7 jours ou moins.{' '}
                  </>
                )}
                {Number(stats.cdp_expired_unpaid_count) > 0 && (
                  <>
                    {stats.cdp_expired_unpaid_count} commandement{stats.cdp_expired_unpaid_count > 1 ? 's' : ''}
                    {' '}échu{stats.cdp_expired_unpaid_count > 1 ? 's' : ''} sans règlement.
                  </>
                )}
              </p>
            </div>
            <span className="text-orange-800 text-sm font-medium">Voir les procédures →</span>
          </div>
        </Link>
      )}

      {/* Stats — 2 rows of 4 cards, taille intermédiaire */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="Biens" value={stats.properties_total} color="blue" />
        <StatCard label="Baux actifs" value={stats.active_leases} color="blue" />
        <StatCard
          label="Loyers payés"
          value={stats.current_month_paid}
          sub={`sur ${stats.active_leases}`}
          color={
            stats.active_leases === 0
              ? 'blue'
              : stats.current_month_paid === 0
                ? 'red'
                : stats.current_month_paid < stats.active_leases
                  ? 'orange'
                  : 'green'
          }
        />
        <StatCard
          label="Impayés / Partiels"
          value={stats.current_month_unpaid}
          color={stats.current_month_unpaid > 0 ? 'red' : 'green'}
        />
        <StatCard label="Loyers attendus" value={fmtCurrency(stats.total_expected)} sub="mois en cours" color="blue" />
        <StatCard label="Loyers reçus" value={fmtCurrency(stats.total_received)} sub="mois en cours" color="green" />
        <StatCard
          label="Solde dû"
          value={fmtCurrency(stats.total_outstanding_current_month ?? stats.total_outstanding)}
          sub={periodLabel}
          color={Number(stats.total_outstanding_current_month ?? stats.total_outstanding) > 0 ? 'red' : 'green'}
        />
        <div className={`bg-white rounded-lg shadow-sm border border-gray-200 border-t-4 px-4 py-3 ${Number(stats.total_outstanding_all_months ?? 0) > 0 ? 'border-red-600 bg-red-100' : 'border-green-500 bg-green-50'}`}>
          <p className="text-sm text-gray-600 font-semibold leading-tight">Solde total impayés</p>
          <p className={`text-2xl font-extrabold leading-tight mt-1 ${Number(stats.total_outstanding_all_months ?? 0) > 0 ? 'text-red-700' : 'text-green-700'}`}>
            {fmtCurrency(stats.total_outstanding_all_months ?? 0)}
          </p>
          <p className="text-xs text-gray-600 leading-tight mt-0.5">tous mois</p>
        </div>
      </div>

      {/* One row per active lease (vacant properties also appear) */}
      <div className="card">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">État des baux</h2>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="table-th">Bien</th>
                <th className="table-th">Locataire</th>
                <th className="table-th">Loyer CC</th>
                <th className="table-th">Statut {periodLabel}</th>
                <th className="table-th">Solde mois en cours</th>
                <th className="table-th">Solde total</th>
                <th className="table-th">Alertes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rows.map((r, idx) => (
                <tr key={r.lease_id ?? `vacant-${r.property_id}-${idx}`} className="hover:bg-gray-50">
                  <td className="table-td">
                    <div className="font-medium text-gray-900">{r.property_name}</div>
                    <div className="text-xs text-gray-400">{propertyTypeLabel(r.property_type)}</div>
                  </td>
                  <td className="table-td">
                    {r.tenant_name ? (
                      r.lease_id
                        ? <Link to={`/leases/${r.lease_id}`} className="text-blue-600 hover:underline">{r.tenant_name}</Link>
                        : <span className="text-gray-700">{r.tenant_name}</span>
                    ) : (
                      <span className="text-gray-400 italic">Vacant</span>
                    )}
                  </td>
                  <td className="table-td">
                    {r.monthly_total != null ? fmtCurrency(r.monthly_total) : '—'}
                  </td>
                  <td className="table-td">
                    {r.current_payment ? (
                      <StatusBadge status={r.current_payment.status} />
                    ) : (
                      <span className="text-gray-400">—</span>
                    )}
                  </td>
                  <td className="table-td">
                    {Number(r.outstanding) > 0
                      ? <span className="text-red-600 font-medium">{fmtCurrency(r.outstanding)}</span>
                      : (r.lease_id ? <span className="text-green-600">0,00 €</span> : <span className="text-gray-400">—</span>)}
                  </td>
                  <td className="table-td">
                    {r.lease_id == null
                      ? <span className="text-gray-400">—</span>
                      : Number(r.outstanding_total ?? 0) > 0
                        ? (
                          <span className="text-red-700 font-bold">
                            {fmtCurrency(r.outstanding_total ?? 0)}
                            {Number(r.outstanding_months_count ?? 0) > 0 && (
                              <span className="ml-1 text-xs font-normal text-red-600">
                                ({r.outstanding_months_count} mois)
                              </span>
                            )}
                          </span>
                        )
                        : <span className="text-green-600">0,00 €</span>}
                  </td>
                  <td className="table-td space-y-1">
                    {r.irl_alert && (
                      <span className="inline-block text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full mr-1">
                        Révision IRL
                      </span>
                    )}
                    {r.notice_alert && (
                      <span className="inline-block text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full mr-1">
                        Préavis bailleur possible
                      </span>
                    )}
                    {r.overdue_alert && (
                      <span className="inline-block text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full mr-1">
                        Paiement en retard
                      </span>
                    )}
                    {!r.irl_alert && !r.notice_alert && !r.overdue_alert && (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
