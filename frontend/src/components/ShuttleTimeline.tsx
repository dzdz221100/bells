import type { Dashboard } from '../types'
import { clock, dayLabel, duration, hhmm, parseLocal } from '../lib/format'
import { LemonMark } from './Lemons'

/**
 * The pickup as a journey rather than a fact: land, clear the airport, be
 * collected, arrive. All four times come from the guest's own row and the
 * solver's run — the only arithmetic here is adding the drive leg the backend
 * sends, so nothing on screen is invented.
 */
export default function ShuttleTimeline({ data }: { data: Dashboard }) {
  const run = data.pickup.run
  const g = data.guest

  if (!run || !g.arrival_at) {
    return (
      <section className="card">
        <div className="card-head">
          <span className="eyebrow">Airport pickup</span>
          <span className="card-rule" />
        </div>
        <p className="empty">
          {g.arrival_at
            ? 'No shuttle booked for you yet.'
            : 'Tell us your flight above and we’ll work out your pickup.'}
        </p>
      </section>
    )
  }

  const landing = parseLocal(g.arrival_at)
  const depart = parseLocal(run.depart_at)
  const wait = data.pickup.minutes_after_landing ?? 0
  const drive = data.pickup.drive_minutes ?? 0
  const arrive = depart ? new Date(depart.getTime() + drive * 60_000) : null

  const steps = [
    {
      time: clock(g.arrival_at),
      title: `You land${g.arrival_flight ? ` on ${g.arrival_flight}` : ''}`,
      sub: landing ? dayLabel(g.arrival_at) : '',
      kind: 'land',
    },
    {
      time: `${wait} min`,
      title: 'Passport and bags',
      sub: 'Time we leave you before the bus goes',
      kind: 'wait',
    },
    {
      time: clock(run.depart_at),
      title: 'Your shuttle leaves',
      sub: run.from_loc,
      kind: 'pickup',
    },
    {
      // formatted from the Date directly: toISOString() would shift to UTC
      time: arrive ? hhmm(arrive) : '—',
      title: 'You arrive',
      sub: `${run.to_loc} · about ${duration(drive)} on the road`,
      kind: 'arrive',
    },
  ]

  return (
    <section className="card journey">
      <LemonMark />
      <div className="card-head">
        <span className="eyebrow">Your journey in</span>
        <span className="card-rule" />
      </div>

      <ol className="journey-steps">
        {steps.map((s) => (
          <li key={s.kind} className={`jstep ${s.kind}`}>
            <span className="jtime">{s.time}</span>
            <span className="jmark" aria-hidden="true" />
            <span className="jbody">
              <b>{s.title}</b>
              <small>{s.sub}</small>
            </span>
          </li>
        ))}
      </ol>

      {data.pickup.be_at_pickup_by && (
        <p className="deadline">
          Be at the pickup point by <strong>{clock(data.pickup.be_at_pickup_by)}</strong>.
        </p>
      )}
      <p className="journey-foot">
        {run.seats_taken} of {run.capacity} seats taken · run {run.id}
      </p>
    </section>
  )
}
