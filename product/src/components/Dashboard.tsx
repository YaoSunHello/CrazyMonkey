import type { RunResult } from '../types'
import './Dashboard.css'

const STATUS_META = [
  { key: 'matched' as const, icon: '✓', label: 'Matched', color: 'var(--status-good)' },
  { key: 'unresolved' as const, icon: '?', label: 'Unresolved', color: 'var(--status-warning)' },
  { key: 'flagged' as const, icon: '!', label: 'Flagged', color: 'var(--status-critical)' },
]

function BarRow({
  label,
  count,
  max,
  color,
  icon,
}: {
  label: string
  count: number
  max: number
  color: string
  icon?: string
}) {
  const pct = max === 0 ? 0 : Math.max((count / max) * 100, count > 0 ? 4 : 0)
  return (
    <div className="bar-row" title={`${label}: ${count}`}>
      <span className="bar-row__label">
        {icon && <span className="bar-row__icon" style={{ color }}>{icon}</span>}
        {label}
      </span>
      <span className="bar-row__track">
        <span
          className="bar-row__fill"
          style={{ width: `${pct}%`, background: color }}
        />
      </span>
      <span className="bar-row__value">{count}</span>
    </div>
  )
}

export default function Dashboard({ result }: { result: RunResult }) {
  const byStatus = {
    matched: result.summary.matched,
    unresolved: result.summary.unresolved,
    flagged: result.summary.flagged,
  }
  const statusMax = Math.max(...Object.values(byStatus), 1)

  const byClassification = new Map<string, number>()
  for (const row of result.rows) {
    byClassification.set(row.classification, (byClassification.get(row.classification) ?? 0) + 1)
  }
  const classMax = Math.max(...Array.from(byClassification.values()), 1)

  return (
    <div className="dashboard">
      <div className="dashboard__panel">
        <h3 className="dashboard__title">Resolution status</h3>
        <div className="bar-list">
          {STATUS_META.map((s) => (
            <BarRow
              key={s.key}
              label={s.label}
              icon={s.icon}
              count={byStatus[s.key]}
              max={statusMax}
              color={s.color}
            />
          ))}
        </div>
      </div>

      <div className="dashboard__panel">
        <h3 className="dashboard__title">By classification</h3>
        <div className="bar-list">
          {Array.from(byClassification.entries()).map(([label, count]) => (
            <BarRow key={label} label={label} count={count} max={classMax} color="var(--accent)" />
          ))}
        </div>
      </div>
    </div>
  )
}
