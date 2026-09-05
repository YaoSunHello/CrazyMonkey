import type { Question } from './types'

// v1 due-diligence question set, drawn from docs/business-case.md. Meant to
// be edited freely — swap, add, or remove questions/categories as needed.
export const questionnaire: Question[] = [
  {
    id: 'mandate-checks',
    category: 'Mandate fit',
    prompt: 'Which of these should this run check?',
    type: 'checkbox-group',
    options: [
      { value: 'ips-bands', label: 'Strategy, sector, and geography sit inside our IPS bands' },
      { value: 'vintage-concentration', label: 'Vintage-year concentration impact' },
      { value: 'leverage-ceiling', label: 'Leverage ceiling compliance' },
      { value: 'exclusion-list', label: 'Conflicts with our exclusion list' },
    ],
  },
  {
    id: 'track-record-checks',
    category: 'Track record',
    prompt: 'Which of these should this run check?',
    type: 'checkbox-group',
    options: [
      { value: 'net-irr-definition', label: 'Net IRR definition (net of what, exactly)' },
      { value: 'tvpi-basis', label: 'TVPI / DPI / RVPI basis (committed vs. contributed)' },
      { value: 'benchmark-consistency', label: 'Benchmark / PME consistency across funds compared' },
    ],
  },
  {
    id: 'fees-checks',
    category: 'Fees & economics',
    prompt: 'Which of these should this run check?',
    type: 'checkbox-group',
    options: [
      { value: 'fee-basis', label: 'Management fee basis and step-down terms' },
      { value: 'fee-offset', label: 'Fee offset percentage' },
      { value: 'carry-waterfall', label: 'Carry waterfall type (European/American) and hurdle' },
    ],
  },
  {
    id: 'legal-checks',
    category: 'Legal & governance',
    prompt: 'Which of these should this run check?',
    type: 'checkbox-group',
    options: [
      { value: 'lpac-rights', label: 'LPAC composition and our representation rights' },
      { value: 'key-person', label: 'Key-person provisions and triggers' },
      { value: 'mfn-flow', label: 'Most-favored-nation clause flow-through' },
    ],
  },
  {
    id: 'operational-checks',
    category: 'Operational / reporting quality',
    prompt: 'Which of these should this run check?',
    type: 'checkbox-group',
    options: [
      { value: 'ilpa-format', label: 'ILPA-standard reporting format vs. proprietary' },
      { value: 'restatement-cycles', label: 'Number of NAV restatement cycles' },
      { value: 'audit-qualifications', label: 'Audit qualification history' },
    ],
  },
  {
    id: 'known-constraints',
    category: 'Additional context',
    prompt: 'Any known mandate constraints for this fund (vintage limits, exclusions, concentration caps)?',
    type: 'text',
    placeholder: 'e.g. no more than 15% in a single vintage year, no fossil fuels exposure...',
  },
]
