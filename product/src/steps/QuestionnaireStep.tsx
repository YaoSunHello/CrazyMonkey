import { usePipeline } from '../PipelineContext'
import { questionnaire } from '../questionnaire.config'
import type { Answer } from '../types'
import './steps.css'

function groupByCategory() {
  const groups = new Map<string, typeof questionnaire>()
  for (const q of questionnaire) {
    const list = groups.get(q.category) ?? []
    list.push(q)
    groups.set(q.category, list)
  }
  return groups
}

export default function QuestionnaireStep({
  onBack,
  onRun,
}: {
  onBack: () => void
  onRun: () => void
}) {
  const { answers, setAnswer } = usePipeline()
  const groups = groupByCategory()

  function toggleCheckbox(questionId: string, value: string) {
    const current = (answers[questionId] as string[] | undefined) ?? []
    const next = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value]
    setAnswer(questionId, next)
  }

  return (
    <div className="step">
      <p className="step__kicker">Step 2 of 4</p>
      <h1 className="step__title">What should this run check?</h1>
      <p className="step__lede">
        Answer what's relevant — this shapes what the agent checks for and flags. Leave the
        rest blank.
      </p>

      {Array.from(groups.entries()).map(([category, questions]) => (
        <section key={category} className="q-group">
          <h2 className="q-group__title">{category}</h2>
          {questions.map((q) => (
            <div key={q.id} className="q-field">
              <p className="q-field__prompt">{q.prompt}</p>
              {q.type === 'checkbox-group' && q.options && (
                <div className="q-field__options">
                  {q.options.map((opt) => {
                    const checked = ((answers[q.id] as string[] | undefined) ?? []).includes(
                      opt.value,
                    )
                    return (
                      <label key={opt.value} className="q-checkbox">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleCheckbox(q.id, opt.value)}
                        />
                        {opt.label}
                      </label>
                    )
                  })}
                </div>
              )}
              {q.type === 'text' && (
                <textarea
                  className="q-textarea"
                  placeholder={q.placeholder}
                  value={(answers[q.id] as Answer | undefined) as string | undefined ?? ''}
                  onChange={(e) => setAnswer(q.id, e.target.value)}
                  rows={2}
                />
              )}
            </div>
          ))}
        </section>
      ))}

      <div className="step__actions">
        <button type="button" className="btn btn--ghost" onClick={onBack}>
          Back
        </button>
        <button type="button" className="btn btn--primary" onClick={onRun}>
          Run Agent →
        </button>
      </div>
    </div>
  )
}
