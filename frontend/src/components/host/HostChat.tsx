import { useEffect, useRef, useState } from 'react'
import { cancelProposal, confirmProposal, sendHostChat } from '../../api'
import Markdown from '../Markdown'
import Trace from '../Trace'
import type { HostProposal, HostReply } from '../../types'

type Msg = {
  id: string
  role: 'user' | 'assistant' | 'error'
  content: string
  reply?: HostReply
  proposals?: HostProposal[]
}

let nextId = 0
const newId = () => `h${nextId++}`

const OPENERS = [
  'Who still hasn’t told us if they’re coming?',
  'What still needs doing?',
  'Remind everyone who hasn’t RSVP’d, gently',
]

/**
 * The couple's concierge. Same shell as the guest chat, with one addition:
 * when the agent proposes a change, it arrives as a card with Do it / Cancel
 * rather than as a sentence asking them to type yes.
 */
export default function HostChat({ onChanged }: { onChanged: () => void }) {
  const [messages, setMessages] = useState<Msg[]>([
    {
      id: newId(),
      role: 'assistant',
      content:
        'Ask me anything about the wedding — or tell me what to change. ' +
        'I’ll always show you a change before it happens.',
    },
  ])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [acting, setActing] = useState<string | null>(null)
  const [resolved, setResolved] = useState<Record<string, 'done' | 'cancelled'>>({})
  const threadRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = threadRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, busy])

  async function send(text: string) {
    const trimmed = text.trim()
    if (!trimmed || busy) return
    setMessages((m) => [...m, { id: newId(), role: 'user', content: trimmed }])
    setDraft('')
    setBusy(true)
    try {
      const reply = await sendHostChat(trimmed)
      setMessages((m) => [
        ...m,
        {
          id: newId(),
          role: 'assistant',
          content: reply.answer,
          reply,
          proposals: reply.proposals,
        },
      ])
      if (reply.committed.length || reply.drafts.length) onChanged()
    } catch (e) {
      setMessages((m) => [...m, { id: newId(), role: 'error', content: (e as Error).message }])
    } finally {
      setBusy(false)
    }
  }

  async function act(p: HostProposal, go: boolean) {
    setActing(p.id)
    try {
      if (go) {
        const res = await confirmProposal(p.id)
        setResolved((r) => ({ ...r, [p.id]: 'done' }))
        setMessages((m) => [
          ...m,
          { id: newId(), role: 'assistant', content: `Done — ${res.summary}` },
        ])
        onChanged()
      } else {
        await cancelProposal(p.id)
        setResolved((r) => ({ ...r, [p.id]: 'cancelled' }))
      }
    } catch (e) {
      setMessages((m) => [...m, { id: newId(), role: 'error', content: (e as Error).message }])
    } finally {
      setActing(null)
    }
  }

  return (
    <section className="panel host-chat">
      <header className="panel-head">
        <div>
          <h2>Ask Bells</h2>
          <p>
            Your side of the concierge. It can see the whole guest list and change
            things — but never without showing you first.
          </p>
        </div>
      </header>

      <div className="thread" ref={threadRef}>
        {messages.map((m) => (
          <div
            key={m.id}
            className={`msg ${m.role === 'user' ? 'user' : m.role === 'error' ? 'bells error' : 'bells'}`}
          >
            <span className="msg-who">{m.role === 'user' ? 'You' : 'Bells'}</span>
            <div className="bubble">
              {m.role === 'assistant' ? <Markdown>{m.content}</Markdown> : m.content}
            </div>

            {m.proposals?.map((p) => {
              const state = resolved[p.id]
              return (
                <article key={p.id} className={`proposal ${state ?? ''}`}>
                  <span className="proposal-kind">{p.kind.replace(/_/g, ' ')}</span>
                  <p className="proposal-summary">{p.summary}</p>

                  {p.before && p.after && (
                    <dl className="proposal-diff">
                      {Object.keys(p.after)
                        .filter((k) => p.after[k] !== undefined && k !== 'fact_id')
                        .slice(0, 3)
                        .map((k) => (
                          <div key={k}>
                            <dt>{k.replace(/_/g, ' ')}</dt>
                            <dd>
                              {p.before[k] != null && String(p.before[k]) !== String(p.after[k]) && (
                                <s>{String(p.before[k]).slice(0, 60)}</s>
                              )}
                              <b>{String(p.after[k]).slice(0, 90)}</b>
                            </dd>
                          </div>
                        ))}
                    </dl>
                  )}

                  {state === 'done' ? (
                    <span className="proposal-state done">Done</span>
                  ) : state === 'cancelled' ? (
                    <span className="proposal-state">Cancelled</span>
                  ) : (
                    <div className="proposal-actions">
                      <button
                        className="btn primary small"
                        disabled={acting === p.id}
                        onClick={() => act(p, true)}
                      >
                        {acting === p.id ? 'Doing it…' : 'Do it'}
                      </button>
                      <button
                        className="btn ghost small"
                        disabled={acting === p.id}
                        onClick={() => act(p, false)}
                      >
                        Cancel
                      </button>
                      <span className="proposal-note">Nothing has changed yet</span>
                    </div>
                  )}
                </article>
              )
            })}

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
                <span>looking…</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {messages.length <= 1 && (
        <div className="suggestions">
          {OPENERS.map((o) => (
            <button key={o} className="chip" disabled={busy} onClick={() => send(o)}>
              {o}
            </button>
          ))}
        </div>
      )}

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault()
          send(draft)
        }}
      >
        <textarea
          rows={1}
          value={draft}
          placeholder="Ask, or tell Bells what to change…"
          onChange={(e) => {
            setDraft(e.target.value)
            e.target.style.height = 'auto'
            e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send(draft)
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
