export interface UploadedFile {
  id: string
  name: string
  size: number
  type: string
}

export type QuestionType = 'checkbox-group' | 'select' | 'text'

export interface QuestionOption {
  value: string
  label: string
}

export interface Question {
  id: string
  category: string
  prompt: string
  type: QuestionType
  options?: QuestionOption[]
  placeholder?: string
}

export type Answer = string | string[]

export type MatchStatus = 'MATCH' | 'UNRESOLVED' | 'FLAGGED'

export interface ExtractedRow {
  id: string
  date: string
  narrative: string
  counterparty: string | null
  projectCode: string | null
  classification: string
  amount: number
  currency: string
  matchStatus: MatchStatus
  confidence_score: number | null
  source_document: string
  source_page: number
  source_snippet: string
}

export interface RunSummary {
  totalRows: number
  matched: number
  unresolved: number
  flagged: number
  documentsProcessed: number
}

export interface RunResult {
  id: string
  generatedAt: string
  summary: RunSummary
  rows: ExtractedRow[]
}

export type StageKey =
  | 'upload'
  | 'classify'
  | 'extract'
  | 'normalize'
  | 'review'
  | 'export'

export interface RunProgress {
  stage: StageKey
  stageIndex: number
  caption: string
  done: boolean
}

export type RunStatus = 'idle' | 'running' | 'done' | 'error'
