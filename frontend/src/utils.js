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
  const m = { rent_receipt: 'Quittance de loyer', lease_scan: 'Scan du bail', other: 'Autre' }
  return m[type] ?? type
}

export function currentYearMonth() {
  const now = new Date()
  return { year: now.getFullYear(), month: now.getMonth() + 1 }
}
