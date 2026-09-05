import { useState } from 'react'
import { answerQuestion } from '../assistant'
import type { RunResult } from '../types'
import './AiAssistantPanel.css'

interface Message {
  id: string
  role: 'user' | 'assistant'
  text: string
}

const GREETING: Message = {
  id: 'greeting',
  role: 'assistant',
  text: "Ask me about this run's data — row counts, a specific counterparty, or why something was flagged. I'll only answer from what's actually in this run, and I'll say so if I can't.",
}

export default function AiAssistantPanel({
  result,
  open,
  onClose,
}: {
  result: RunResult
  open: boolean
  onClose: () => void
}) {
  const [messages, setMessages] = useState<Message[]>([GREETING])
  const [input, setInput] = useState('')

  function send() {
    const query = input.trim()
    if (!query) return
    const answer = answerQuestion(query, result)
    setMessages((prev) => [
      ...prev,
      { id: `u-${prev.length}`, role: 'user', text: query },
      { id: `a-${prev.length + 1}`, role: 'assistant', text: answer.text },
    ])
    setInput('')
  }

  if (!open) return null

  return (
    <div className="ai-panel">
      <div className="ai-panel__header">
        <span>Ask about this dataset</span>
        <button type="button" className="ai-panel__close" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>

      <div className="ai-panel__messages">
        {messages.map((m) => (
          <div key={m.id} className={`ai-msg ai-msg--${m.role}`}>
            {m.text}
          </div>
        ))}
      </div>

      <form
        className="ai-panel__input"
        onSubmit={(e) => {
          e.preventDefault()
          send()
        }}
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. how many rows are unresolved?"
        />
        <button type="submit" className="btn btn--primary">
          Ask
        </button>
      </form>
    </div>
  )
}
