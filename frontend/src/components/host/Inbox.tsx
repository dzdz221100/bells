import { useState } from 'react'
import type { Escalation } from '../../types'
import { languageName } from '../../lib/format'

type Props = {
  items: Escalation[]
  loading: boolean
  busyId: number | null
  onApprove: (e: Escalation, answer: string, topic?: string) => void
  onDismiss: (e: Escalation) => void
}

function ago(iso: string): string {
  const then = new Date(iso.replace(' ', 'T')).getTime()
  if (Number.isNaN(then)) return ''
  const mins = Math.round((Date.now() - then) / 60000)
  if (mins < 0) return new Date(then).toLocaleDateString()
  if (mins < 60) return `${mins} min ago`
  if (mins < 1440) return `${Math.round(mins / 60)} h ago`
  return `${Math.round(mins / 1440)} d ago`
}

function Card({ item, busy, onApprove, onDismiss }: {
  item: Escalation
  busy: boolean
  onApprove: Props['onApprove']
  onDismiss: Props['onDismiss']
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(item.draft_answer ?? '')
  const hasDraft = Boolean(item.draft_answer?.trim())

  return (
    <article className="esc">
      <div className="esc-top">
        <div>
          <span className="esc-guest">{item.guest_name ?? 'A guest'}</span>
          {item.guest_language && (
            <span className="lang-chip">{languageName(item.guest_language)}</span>
          )}
        </div>
        <span className="esc-age">{ago(item.created_at)}</span>
      </div>

      <p className="esc-q">“{item.question}”</p>

      <div className="esc-draft">
        <span className="esc-draft-label">Bells’ draft</span>
        {editing ? (
          <textarea
            className="esc-edit"
            value={draft}
            autoFocus
            rows={5}
            placeholder="Write the answer guests will get from now on…"
            onChange={(e) => setDraft(e.target.value)}
          />
        ) : hasDraft ? (
          <p>{item.draft_answer}</p>
        ) : (
          <p className="empty">
            No draft — Bells had nothing recorded to go on. Write the answer yourself.
          </p>
        )}
      </div>

      <div className="esc-actions">
        {editing ? (
          <>
            <button
              className="btn primary"
              disabled={busy || !draft.trim()}
              onClick={() => onApprove(item, draft)}
            >
              Save &amp; approve
            </button>
            <button className="btn ghost" disabled={busy} onClick={() => setEditing(false)}>
              Cancel
            </button>
          </>
        ) : (
          <>
            <button
              className="btn primary"
              disabled={busy || !hasDraft}
              title={hasDraft ? undefined : 'There is no draft to approve — edit it first'}
              onClick={() => onApprove(item, item.draft_answer ?? '')}
            >
              Approve
            </button>
            <button
              className="btn"
              disabled={busy}
              onClick={() => {
                setDraft(item.draft_answer ?? '')
                setEditing(true)
              }}
            >
              Edit &amp; approve
            </button>
            <button className="btn ghost" disabled={busy} onClick={() => onDismiss(item)}>
              Dismiss
            </button>
          </>
        )}
        <span className="esc-note">Approving saves it as a fact Bells can reuse.</span>
      </div>
    </article>
  )
}

export default function Inbox({ items, loading, busyId, onApprove, onDismiss }: Props) {
  return (
    <section className="panel inbox">
      <header className="panel-head">
        <div>
          <h2>Inbox</h2>
          <p>Questions Bells couldn’t answer. Your answer becomes its answer.</p>
        </div>
        <span className="count-pill">{items.length} open</span>
      </header>

      <div className="panel-body">
        {loading ? (
          <div className="skeleton" style={{ height: 150 }} />
        ) : items.length === 0 ? (
          <div className="inbox-clear">
            <span className="tick" aria-hidden="true" />
            <h3>Nothing waiting</h3>
            <p>Bells has answered everything guests have asked so far.</p>
          </div>
        ) : (
          items.map((e) => (
            <Card
              key={e.id}
              item={e}
              busy={busyId === e.id}
              onApprove={onApprove}
              onDismiss={onDismiss}
            />
          ))
        )}
      </div>
    </section>
  )
}
