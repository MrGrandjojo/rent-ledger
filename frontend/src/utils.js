export const MONTHS_FR = [
  '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
  'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
]

export function fmtCurrency(value) {
  return new Intl.NumberFormat('fr-FR', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 2,
  }).format(Number(value))
}

export function fmtDate(dateStr) {
  if (!dateStr) return '—'
  const [y, m, d] = dateStr.split('-')
  return `${d}/${m}/${y}`
}

export function fmtDatetime(dtStr) {
  if (!dtStr) return '—'
  const d = new Date(dtStr)
  return d.toLocaleString('fr-FR', { timeZone: 'Europe/Paris', dateStyle: 'short', timeStyle: 'short' })
}

export function propertyTypeLabel(type) {
  return type === 'apartment' ? 'Appartement' : type === 'parking' ? 'Parking' : type
}

export function leaseTypeLabel(type) {
  const m = {
    unfurnished: 'Non meublé',
    furnished: 'Meublé',
    furnished_student: 'Meublé étudiant',
  }
  return m[type] ?? type
}

export function revisionReasonLabel(reason) {
  const m = {
    initial: 'Initiale',
    irl_revision: 'Révision IRL',
    amicable: 'Amiable',
    other: 'Autre',
  }
  return m[reason] ?? reason
}

export function docTypeLabel(type) {
  const m = {
    rent_receipt: 'Quittance de loyer',
    lease_scan: 'Scan du bail',
    commandement_payer: 'Commandement de payer',
    other: 'Autre',
  }
  return m[type] ?? type
}

export function procedureTypeLabel(type) {
  const m = { commandement_payer: 'Commandement de payer' }
  return m[type] ?? type
}

export function procedureStatusLabel(status) {
  const m = {
    in_progress: 'En cours',
    paid: 'Payé',
    expired_unpaid: 'Échu impayé',
    cancelled: 'Annulé',
  }
  return m[status] ?? status
}

export function procedureStatusClass(status) {
  switch (status) {
    case 'paid':
      return 'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800'
    case 'expired_unpaid':
      return 'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800'
    case 'cancelled':
      return 'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-200 text-gray-700'
    case 'in_progress':
    default:
      return 'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800'
  }
}

// Add `n` calendar months to an ISO date (YYYY-MM-DD), clamping the day
// to the new month's last day. Returns an ISO date string.
export function addMonthsISO(isoDate, n) {
  if (!isoDate) return ''
  const [y, m, d] = isoDate.split('-').map(Number)
  const totalMonths = (m - 1) + n
  const newYear = y + Math.floor(totalMonths / 12)
  const newMonth = (totalMonths % 12) + 1
  // Last day of new month
  const lastDay = new Date(newYear, newMonth, 0).getDate()
  const newDay = Math.min(d, lastDay)
  return `${newYear}-${String(newMonth).padStart(2, '0')}-${String(newDay).padStart(2, '0')}`
}

export function currentYearMonth() {
  const now = new Date()
  return { year: now.getFullYear(), month: now.getMonth() + 1 }
}
