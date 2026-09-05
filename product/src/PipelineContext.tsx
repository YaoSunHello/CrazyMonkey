import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import type { Answer, RunProgress, RunResult, RunStatus, UploadedFile } from './types'

interface PipelineState {
  rawFiles: File[]
  files: UploadedFile[]
  answers: Record<string, Answer>
  runStatus: RunStatus
  progress: RunProgress | null
  result: RunResult | null
}

interface PipelineContextValue extends PipelineState {
  setRawFiles: (files: File[]) => void
  setFiles: (files: UploadedFile[]) => void
  setAnswer: (id: string, value: Answer) => void
  setRunStatus: (status: RunStatus) => void
  setProgress: (progress: RunProgress | null) => void
  setResult: (result: RunResult | null) => void
  reset: () => void
}

const STORAGE_KEY = 'crazymonkey-product-run'

function loadPersisted(): Pick<PipelineState, 'answers' | 'result'> {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return { answers: {}, result: null }
    const parsed = JSON.parse(raw)
    return { answers: parsed.answers ?? {}, result: parsed.result ?? null }
  } catch {
    return { answers: {}, result: null }
  }
}

function persist(answers: Record<string, Answer>, result: RunResult | null) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ answers, result }))
  } catch {
    // sessionStorage unavailable — fine, this is a convenience only.
  }
}

const PipelineContext = createContext<PipelineContextValue | null>(null)

export function PipelineProvider({ children }: { children: ReactNode }) {
  const persisted = useMemo(loadPersisted, [])
  const [rawFiles, setRawFiles] = useState<File[]>([])
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [answers, setAnswers] = useState<Record<string, Answer>>(persisted.answers)
  const [runStatus, setRunStatus] = useState<RunStatus>('idle')
  const [progress, setProgress] = useState<RunProgress | null>(null)
  const [result, setResult] = useState<RunResult | null>(persisted.result)

  function setAnswer(id: string, value: Answer) {
    setAnswers((prev) => {
      const next = { ...prev, [id]: value }
      persist(next, result)
      return next
    })
  }

  function updateResult(next: RunResult | null) {
    setResult(next)
    persist(answers, next)
  }

  function reset() {
    setRawFiles([])
    setFiles([])
    setAnswers({})
    setRunStatus('idle')
    setProgress(null)
    setResult(null)
    persist({}, null)
  }

  const value: PipelineContextValue = {
    rawFiles,
    files,
    answers,
    runStatus,
    progress,
    result,
    setRawFiles,
    setFiles,
    setAnswer,
    setRunStatus,
    setProgress,
    setResult: updateResult,
    reset,
  }

  return <PipelineContext.Provider value={value}>{children}</PipelineContext.Provider>
}

export function usePipeline() {
  const ctx = useContext(PipelineContext)
  if (!ctx) throw new Error('usePipeline must be used within PipelineProvider')
  return ctx
}
