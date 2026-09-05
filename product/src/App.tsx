import { useState } from 'react'
import { PipelineProvider, usePipeline } from './PipelineContext'
import UploadStep from './steps/UploadStep'
import QuestionnaireStep from './steps/QuestionnaireStep'
import RunStep from './steps/RunStep'
import OutputStep from './steps/OutputStep'
import './App.css'

type Step = 'upload' | 'questionnaire' | 'run' | 'output'

const STEP_ORDER: Step[] = ['upload', 'questionnaire', 'run', 'output']
const STEP_LABELS: Record<Step, string> = {
  upload: 'Upload',
  questionnaire: 'Questionnaire',
  run: 'Run',
  output: 'Output',
}

function Wizard() {
  const [step, setStep] = useState<Step>('upload')
  const { reset } = usePipeline()
  const currentIndex = STEP_ORDER.indexOf(step)

  function startOver() {
    reset()
    setStep('upload')
  }

  return (
    <div className="product-shell">
      <header className="product-header">
        <a href="/" className="product-header__brand">
          🐒 CrazyMonkey
        </a>
        <ol className="step-indicator">
          {STEP_ORDER.map((s, i) => (
            <li
              key={s}
              className={`step-indicator__item${i === currentIndex ? ' step-indicator__item--active' : ''}${i < currentIndex ? ' step-indicator__item--done' : ''}`}
            >
              {STEP_LABELS[s]}
            </li>
          ))}
        </ol>
      </header>

      <main>
        {step === 'upload' && <UploadStep onContinue={() => setStep('questionnaire')} />}
        {step === 'questionnaire' && (
          <QuestionnaireStep onBack={() => setStep('upload')} onRun={() => setStep('run')} />
        )}
        {step === 'run' && <RunStep onDone={() => setStep('output')} />}
        {step === 'output' && <OutputStep onStartOver={startOver} />}
      </main>
    </div>
  )
}

function App() {
  return (
    <PipelineProvider>
      <Wizard />
    </PipelineProvider>
  )
}

export default App
