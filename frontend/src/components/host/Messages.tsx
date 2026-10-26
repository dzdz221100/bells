import { useState } from 'react'
import { approveAllDrafts, approveDraft, skipDraft } from '../../api'
import type { DraftBundle, MessageDraft } from '../../types'
import { languageName } from '../../lib/format'

const SEGMENT_LABEL: Record<string, string> = {
  all: 'Everyone',
  attending: 'Coming',
  not_rsvpd: 'No reply yet',
  declined: 'Can’t come',
  no_flight: 'No flight sent',
  unbooked_hotel: 'No room booked',
}

function Draft({
  draft,
  busy,
  onApprove,
  onSkip,
}: {
  draft: MessageDraft
  busy: boolean
  onApprove: (text: string) => void
  onSkip: () => void
}) {
  const [text, setText] = useState(draft.message)
  const [editing, setEditing] = useState(false)
  const settled = draft.status === 'sent' || draft.status === 'skipped'

  return (
    <article className={`draft ${draft.status}`}>
      <header className="draft-head">
        <span className="draft-name">{draft.name}</span>
        <span className="lang-chip">{languageName(draft.language)}</span>
        <span className="draft-situation">{draft.situation}</span>
      </header>

      {editing && !settled ? (
        <textarea
          className="draft-edit"
          value={text}
          rows={4}
          autoFocus
          onChange={(e) => setText(e.target.value)}
        />
      ) : (
        <p className="draft-body" onClick={() => !settled && setEditing(true)}>
          {text}
        </p>
      )}

      {settled ? (
        <span className={`draft-state ${draft.status}`}>
          {draft.status === 'sent' ? 'Approved — ready to send' : 'Skipped'}
        </span>
      ) : (
        <div className="draft-actions">
          <button className="btn primary small" disabled={busy} onClick={() => onApprove(text)}>
            Approve
          </button>
          <button className="btn ghost small" disabled={busy} onClick={onSkip}>
            Skip
          </button>
          {!editing && (
            <button className="linkish" onClick={() => setEditing(true)}>
              Edit
            </button>
          )}
        </div>
      )}
    </article>
  )
}

export default function Messages({
  bundle,
  onChanged,
}: {
  bundle: DraftBundle | null
  onChanged: () => void
}) {
  const [busy, setBusy] = useState(false)

  if (!bundle || bundle.total === 0) {
    return (
      <section className="panel messages">
        <header className="panel-head">
          <div>
            <h2>Messages</h2>
            <p>Ask Bells to remind or tell a group something, and the drafts land here.</p>
          </div>
        </header>
        <div className="panel-body">
          <p className="empty">
            No drafts yet. Try: “remind everyone who hasn’t RSVP’d, gently”.
          </p>
        </div>
      </section>
    )
  }

  async function run(fn: () => Promise<unknown>) {
    setBusy(true)
    try {
      await fn()
      onChanged()
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel messages">
      <header className="panel-head">
        <div>
          <h2>Messages</h2>
          <p>
            One message per guest, in their own language. Nothing sends by itself —
            approving marks it ready.
          </p>
        </div>
        <span className="count-pill">{bundle.awaiting} awaiting</span>
      </header>

      <div className="panel-body">
        {bundle.segments.map((seg) => {
          const waiting = seg.drafts.filter((d) => d.status === 'draft').length
          return (
            <div className="draft-group" key={seg.segment}>
              <header className="draft-group-head">
                <div>
                  <span className="eyebrow">{SEGMENT_LABEL[seg.segment] ?? seg.segment}</span>
                  <p className="draft-intent">“{seg.intent}”</p>
                </div>
                {waiting > 1 && (
                  <button
                    className="btn small"
                    disabled={busy}
                    onClick={() => run(() => approveAllDrafts(seg.segment))}
                  >
                    Approve all {waiting}
                  </button>
                )}
              </header>

              {seg.drafts.map((d) => (
                <Draft
                  key={d.id}
                  draft={d}
                  busy={busy}
                  onApprove={(text) => run(() => approveDraft(d.id, text))}
                  onSkip={() => run(() => skipDraft(d.id))}
                />
              ))}
            </div>
          )
        })}

        <p className="notice">
          Approving marks a message ready and records it in the audit trail. <b>Bells
          does not send anything</b> — there is no WhatsApp or email sender wired up,
          deliberately, so a demo can never message real guests.
        </p>
      </div>
    </section>
  )
}
