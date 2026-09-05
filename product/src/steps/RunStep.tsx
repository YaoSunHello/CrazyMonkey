import { useEffect, useRef } from 'react'
import RunAnimation from '../components/RunAnimation'
import { usePipeline } from '../PipelineContext'
import { runPipeline } from '../pipeline'
import './steps.css'

export default function RunStep({ onDone }: { onDone: () => void }) {
  const { files, answers, progress, setProgress, setRunStatus, setResult } = usePipeline()
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true
    setRunStatus('running')
    runPipeline(files, answers, setProgress).then((result) => {
      setResult(result)
      setRunStatus('done')
      onDone()
    })
    // Runs once on mount — intentionally not re-triggered by prop/state churn.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="step">
      <p className="step__kicker">Step 3 of 4</p>
      <h1 className="step__title">Running the agent</h1>
      <p className="step__lede">
        Upload → Classify → Extract → Normalize → Review → Export — every field stays
        traceable back to its source.
      </p>
      <RunAnimation progress={progress} />
    </div>
  )
}
