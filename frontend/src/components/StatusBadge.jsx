const LABELS = {
  paid:    'Payé',
  partial: 'Partiel',
  unpaid:  'Impayé',
  pending: 'En cours',
}

const CLS = {
  paid:    'badge-paid',
  partial: 'badge-partial',
  unpaid:  'badge-unpaid',
  pending: 'inline-block px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700',
}

export default function StatusBadge({ status }) {
  const cls = CLS[status] ?? 'badge-unpaid'
  return <span className={cls}>{LABELS[status] ?? status}</span>
}
