import { Fragment, useState } from 'react'
import AiAssistantPanel from '../components/AiAssistantPanel'
import Dashboard from '../components/Dashboard'
import { usePipeline } from '../PipelineContext'
import type { ExtractedRow, MatchStatus, RunResult } from '../types'
import './steps.css'

const STATUS_BADGE: Record<MatchStatus, { label: string; className: string }> = {
  MATCH: { label: '✓ Match', className: 'badge badge--good' },
  UNRESOLVED: { label: '? Unresolved', className: 'badge badge--warning' },
  FLAGGED: { label: '! Flagged', className: 'badge badge--critical' },
}

const CSV_COLUMNS: (keyof ExtractedRow)[] = [
  'date',
  'narrative',
  'counterparty',
  'projectCode',
  'classification',
  'amount',
  'currency',
  'matchStatus',
  'confidence_score',
  'source_document',
  'source_page',
  'source_snippet',
]

function toCsv(result: RunResult): string {
  const header = CSV_COLUMNS.join(',')
  const lines = result.rows.map((row) =>
    CSV_COLUMNS.map((col) => {
      const value = row[col]
      const str = value === null || value === undefined ? '' : String(value)
      return /[",\n]/.test(str) ? `"${str.replace(/"/g, '""')}"` : str
    }).join(','),
  )
  return [header, ...lines].join('\n')
}

function download(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export default function OutputStep({ onStartOver }: { onStartOver: () => void }) {
  const { result } = usePipeline()
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [assistantOpen, setAssistantOpen] = useState(false)

  if (!result) {
    return (
      <div className="step">
        <p>No result yet.</p>
        <button type="button" className="btn btn--primary" onClick={onStartOver}>
          Start over
        </button>
      </div>
    )
  }

  const { summary } = result

  return (
    <div className="step step--wide">
      <p className="step__kicker">Step 4 of 4</p>
      <h1 className="step__title">Structured dataset</h1>
      <p className="step__lede">
        Every row is source-cited. Rows that couldn't be matched are reported as{' '}
        <code>UNRESOLVED</code>, never guessed.
      </p>

      <div className="stat-tiles">
        <div className="stat-tile">
          <span className="stat-tile__label">Total rows</span>
          <span className="stat-tile__value">{summary.totalRows}</span>
        </div>
        <div className="stat-tile">
          <span className="stat-tile__label">Matched</span>
          <span className="stat-tile__value" style={{ color: 'var(--status-good)' }}>
            {summary.matched}
          </span>
        </div>
        <div className="stat-tile">
          <span className="stat-tile__label">Unresolved</span>
          <span className="stat-tile__value" style={{ color: 'var(--status-warning)' }}>
            {summary.unresolved}
          </span>
        </div>
        <div className="stat-tile">
          <span className="stat-tile__label">Flagged</span>
          <span className="stat-tile__value" style={{ color: 'var(--status-critical)' }}>
            {summary.flagged}
          </span>
        </div>
        <div className="stat-tile">
          <span className="stat-tile__label">Documents</span>
          <span className="stat-tile__value">{summary.documentsProcessed}</span>
        </div>
      </div>

      <div className="step__actions step__actions--left">
        <button
          type="button"
          className="btn btn--ghost"
          onClick={() => download(`${result.id}.csv`, toCsv(result), 'text/csv')}
        >
          Download CSV
        </button>
        <button
          type="button"
          className="btn btn--ghost"
          onClick={() =>
            download(`${result.id}.json`, JSON.stringify(result, null, 2), 'application/json')
          }
        >
          Download JSON
        </button>
        <button type="button" className="btn btn--ghost" onClick={onStartOver}>
          Start a new run
        </button>
      </div>

      <h2 className="section-heading">Dashboard</h2>
      <Dashboard result={result} />

      <h2 className="section-heading">Rows</h2>
      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Narrative</th>
              <th>Counterparty</th>
              <th>Classification</th>
              <th>Amount</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row) => {
              const badge = STATUS_BADGE[row.matchStatus]
              const expanded = expandedId === row.id
              return (
                <Fragment key={row.id}>
                  <tr
                    className="data-table__row"
                    onClick={() => setExpandedId(expanded ? null : row.id)}
                  >
                    <td>{row.date}</td>
                    <td className="data-table__narrative">{row.narrative}</td>
                    <td>{row.counterparty ?? '—'}</td>
                    <td>{row.classification}</td>
                    <td className="data-table__amount">
                      {row.amount.toLocaleString()} {row.currency}
                    </td>
                    <td>
                      <span className={badge.className}>{badge.label}</span>
                    </td>
                  </tr>
                  {expanded && (
                    <tr className="data-table__detail-row">
                      <td colSpan={6}>
                        <div className="data-table__detail">
                          <p>
                            <strong>Source:</strong> {row.source_document}, page {row.source_page}
                          </p>
                          <p>
                            <strong>Snippet:</strong> "{row.source_snippet}"
                          </p>
                          <p>
                            <strong>Confidence:</strong>{' '}
                            {row.confidence_score !== null
                              ? `${Math.round(row.confidence_score * 100)}%`
                              : 'n/a'}
                          </p>
                          <p>
                            <strong>Project code:</strong> {row.projectCode ?? 'unresolved'}
                          </p>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>

      <button
        type="button"
        className="ask-ai-fab"
        onClick={() => setAssistantOpen(true)}
      >
        Ask AI
      </button>

      <AiAssistantPanel
        result={result}
        open={assistantOpen}
        onClose={() => setAssistantOpen(false)}
      />
    </div>
  )
}
