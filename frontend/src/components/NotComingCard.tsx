import type { Dashboard } from '../types'
import { LemonMark } from './Lemons'

/**
 * What a guest who can't come sees instead of their hotel and pickup.
 *
 * Their shuttle seat has already been released server-side, so showing a
 * departure time would be a lie. The registry and the chat stay — people who
 * can't come still send gifts and still have questions.
 */
export default function NotComingCard({ data }: { data: Dashboard }) {
  const first = data.guest.name.split(' ')[0]
  return (
    <section className="card not-coming">
      <LemonMark />
      <div className="card-head">
        <span className="eyebrow">Your plans</span>
        <span className="card-rule" />
      </div>
      <h3 className="card-title">We'll miss you, {first}</h3>
      <p className="card-sub">
        You've told the couple you can't make it, so there's no room block or
        airport pickup held for you — the seat you had has gone back to the pool
        for another guest.
      </p>
      <p className="card-sub" style={{ marginTop: 10 }}>
        If that changes, hit <strong>Changed your mind?</strong> below and Bells
        will find you a hotel and a shuttle again. You can still send a gift
        from the registry, and you can still ask Bells anything.
      </p>
    </section>
  )
}
