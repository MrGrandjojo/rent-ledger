export default function AlertBanner({ type = 'warning', children }) {
  const colors = {
    warning: 'bg-amber-50 border-amber-400 text-amber-800',
    danger:  'bg-red-50 border-red-400 text-red-800',
    info:    'bg-blue-50 border-blue-400 text-blue-800',
  }
  return (
    <div className={`flex items-start gap-3 px-4 py-3 rounded-lg border-l-4 text-sm ${colors[type]}`}>
      <span>{type === 'warning' ? '⚠️' : type === 'danger' ? '🚨' : 'ℹ️'}</span>
      <div>{children}</div>
    </div>
  )
}
