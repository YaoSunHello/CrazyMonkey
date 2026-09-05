import type { RunResult } from './types'

export interface AssistantAnswer {
  text: string
  citedRowIds: string[]
}

const PREDICTIVE_PATTERN =
  /\b(next quarter|next year|forecast|predict|projected|will be|going to be|expect.*to (be|reach))\b/i
const MANDATE_PATTERN = /\b(mandate|esg|exclusion|compliance|ips|policy)\b/i

// Guardrails from docs/business-case.md §5: never fabricate a citation,
// never silently resolve an UNRESOLVED row, and explicitly refuse anything
// this run's data can't answer — predictive questions, mandate/compliance
// checks with no mandate document in this run, and anything with no match
// in the extracted rows.
export function answerQuestion(query: string, result: RunResult): AssistantAnswer {
  const q = query.trim().toLowerCase()

  if (!q) {
    return {
      text: "Ask me about this run's extracted data — row counts, a specific counterparty or project code, or why a value was flagged.",
      citedRowIds: [],
    }
  }

  if (PREDICTIVE_PATTERN.test(q)) {
    return {
      text: "I can't answer that — it asks about a future period. This run only contains data extracted from the documents you uploaded, so I don't forecast.",
      citedRowIds: [],
    }
  }

  if (MANDATE_PATTERN.test(q)) {
    return {
      text: "I don't have a mandate, exclusion-list, or IPS document in this run to check that against, so I can't answer it. Upload the mandate document, or note the constraint in the questionnaire, and I can check against it directly.",
      citedRowIds: [],
    }
  }

  if (/how many.*unresolved|unresolved.*count/.test(q)) {
    const rows = result.rows.filter((r) => r.matchStatus === 'UNRESOLVED')
    return {
      text: `${result.summary.unresolved} of ${result.summary.totalRows} rows are unresolved — no counterparty or project code match was found for them. These are reported as-is, not guessed.`,
      citedRowIds: rows.map((r) => r.id),
    }
  }

  if (/how many.*flagged|flagged.*count/.test(q)) {
    const rows = result.rows.filter((r) => r.matchStatus === 'FLAGGED')
    return {
      text: `${result.summary.flagged} rows are flagged for review.`,
      citedRowIds: rows.map((r) => r.id),
    }
  }

  if (/how many.*(match|resolved)/.test(q)) {
    const rows = result.rows.filter((r) => r.matchStatus === 'MATCH')
    return {
      text: `${result.summary.matched} of ${result.summary.totalRows} rows matched cleanly against the master lists.`,
      citedRowIds: rows.map((r) => r.id),
    }
  }

  if (/how many.*(document|file|statement)/.test(q)) {
    return {
      text: `${result.summary.documentsProcessed} source documents were processed in this run.`,
      citedRowIds: [],
    }
  }

  if (/how many.*(row|transaction|line)/.test(q)) {
    return {
      text: `${result.summary.totalRows} rows were extracted in this run.`,
      citedRowIds: [],
    }
  }

  const matches = result.rows.filter(
    (r) =>
      (r.counterparty && r.counterparty.toLowerCase().includes(q)) ||
      (r.projectCode && r.projectCode.toLowerCase().includes(q)) ||
      r.narrative.toLowerCase().includes(q) ||
      r.source_document.toLowerCase().includes(q),
  )

  if (matches.length > 0) {
    const lines = matches
      .slice(0, 5)
      .map(
        (r) =>
          `• ${r.date} — ${r.amount.toLocaleString()} ${r.currency} (${r.matchStatus}) — source: ${r.source_document}, p.${r.source_page}: "${r.source_snippet}"`,
      )
    const more = matches.length > 5 ? `\n…and ${matches.length - 5} more.` : ''
    return {
      text: `Found ${matches.length} matching row${matches.length > 1 ? 's' : ''}:\n${lines.join('\n')}${more}`,
      citedRowIds: matches.map((r) => r.id),
    }
  }

  return {
    text: "I don't have that information in this run's extracted data. I can only answer from what was uploaded and processed here — try asking about row counts, a specific counterparty or project code, or a source document.",
    citedRowIds: [],
  }
}
