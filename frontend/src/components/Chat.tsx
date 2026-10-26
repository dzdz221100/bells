import { useEffect, useRef, useState } from 'react'
import type { ChatMessage } from '../types'
import Markdown from './Markdown'
import Trace from './Trace'

type Props = {
  messages: ChatMessage[]
  busy: boolean
  guestName: string
  suggestions: string[]
  onSend: (text: string) => void
  /** rendered inside the dock/sheet, so the header is handled outside */
  compact?: boolean
  onClose?: () => void
}

export default function Chat({
  messages, busy, guestName, suggestions, onSend, compact, onClose,
}: Props) {
  const [draft, setDraft] = useState('')
  const threadRef = useRef<HTMLDivElement>(null)
  const boxRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const el = threadRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, busy])

  function submit(text: string) {
    const trimmed = text.trim()
    if (!trimmed || busy) return
    onSend(trimmed)
    setDraft('')
    if (boxRef.current) boxRef.current.style.height = 'auto'
  }

  return (
    <section className={`chat ${compact ? 'compact' : ''}`}>
      <div className="chat-head">
        {onClose && (
          <button className="sheet-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        )}
        <h2>Ask Bells</h2>
        <p>
          Your concierge for everything about the wedding — it answers only from what{' '}
          the couple have written down, and asks them when it doesn’t know.
        </p>
        <p className="lang-note">
          <span className="globe" aria-hidden="true" />
          Write in any language — English, Italian, French, Spanish, German — and Bells
          replies in the one you used.
        </p>
      </div>

      <div className="thread" ref={threadRef}>
        {messages.map((m) => (
          <div key={m.id} className={`msg ${m.role === 'user' ? 'user' : m.role === 'error' ? 'bells error' : 'bells'}`}>
            <span className="msg-who">{m.role === 'user' ? guestName : 'Bells'}</span>
            <div className="bubble">
              {/* assistant replies are markdown; the guest's own text is not */}
              {m.role === 'assistant' ? <Markdown>{m.content}</Markdown> : m.content}
            </div>
            {m.reply && <Trace reply={m.reply} />}
          </div>
        ))}

        {busy && (
          <div className="msg bells">
            <span className="msg-who">Bells</span>
            <div className="bubble">
              <div className="thinking">
                <span className="dots" aria-hidden="true">
                  <i /> <i /> <i />
                </span>
                <span>checking with the couple’s records…</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {suggestions.length > 0 && (
        <div className="suggestions">
          {suggestions.map((s) => (
            <button key={s} className="chip" disabled={busy} onClick={() => submit(s)}>
              {s}
            </button>
          ))}
        </div>
      )}

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault()
          submit(draft)
        }}
      >
        <textarea
          ref={boxRef}
          rows={1}
          value={draft}
          placeholder="Ask Bells anything…"
          onChange={(e) => {
            setDraft(e.target.value)
            e.target.style.height = 'auto'
            e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              submit(draft)
            }
          }}
        />
        <button className="send" type="submit" disabled={busy || !draft.trim()}>
          Send
        </button>
      </form>
    </section>
  )
}
