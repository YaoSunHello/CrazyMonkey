import { mockResult } from './mockData'
import type { RunProgress, RunResult, StageKey, UploadedFile } from './types'

const STAGES: { key: StageKey; captions: string[] }[] = [
  { key: 'upload', captions: ['Reading uploaded files…', 'Checking file types and sizes…'] },
  { key: 'classify', captions: ['Classifying each document…', 'Identifying statement vs. workbook vs. report…'] },
  { key: 'extract', captions: ['Pulling tables and line items…', 'Recording page and cell references…'] },
  { key: 'normalize', captions: ['Mapping counterparties and project codes…', 'Matching against master lists…'] },
  { key: 'review', captions: ['Checking that numbers foot…', 'Flagging low-confidence fields…'] },
  { key: 'export', captions: ['Building the structured dataset…', 'Finalizing source citations…'] },
]

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

let counter = 0
function nextId() {
  counter += 1
  return `file-${Date.now()}-${counter}`
}

// Real signature a fetch-based adapter would implement too — swap this
// function's body for an API call later without touching any caller.
export async function detectFiles(files: File[]): Promise<UploadedFile[]> {
  return files.map((file) => ({
    id: nextId(),
    name: file.name,
    size: file.size,
    type: file.type || 'application/octet-stream',
  }))
}

// Same shape a real polling/SSE-backed run would have: fire onProgress as
// stages advance, resolve with the final result.
export async function runPipeline(
  _files: UploadedFile[],
  _answers: Record<string, string | string[]>,
  onProgress: (progress: RunProgress) => void,
): Promise<RunResult> {
  for (let i = 0; i < STAGES.length; i += 1) {
    const stage = STAGES[i]
    for (const caption of stage.captions) {
      onProgress({ stage: stage.key, stageIndex: i, caption, done: false })
      await delay(550)
    }
  }
  onProgress({
    stage: STAGES[STAGES.length - 1].key,
    stageIndex: STAGES.length - 1,
    caption: 'Done.',
    done: true,
  })
  return mockResult
}

export const stageOrder: StageKey[] = STAGES.map((s) => s.key)
