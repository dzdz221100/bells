import { useState } from 'react'
import { updateRsvp, updateTravel } from '../api'
import type { Dashboard } from '../types'
import { daysUntil, longDate } from '../lib/format'

type Props = {
  data: Dashboard
  onDone: () => void
  onToast: (text: string, tone?: 'ok' | 'plain') => void
}

type TaskKey = 'rsvp' | 'hotel' | 'flight'

/**
 * What this guest still owes, computed from their own row.
 *
 * Three months out, on a phone, in another country, the only question that
 * matters is "what do I have to do, and when". So this sits directly under the
 * hero, above everything else, and each item resolves in place — no new page,
 * no scrolling off to find a form.
 */
export default function ThreeThings({ data, onDone, onToast }: Props) {
  const g = data.guest
  const hotel = data.hotel
  const [open, setOpen] = useState<TaskKey | null>(null)
  const [busy, setBusy] = useState(false)

  // the flight form's own state
  const [flightNo, setFlightNo] = useState('')
  const [flightDate, setFlightDate] = useState('')
  const [flightTime, setFlightTime] = useState('')

  const declined = g.rsvp_status === 'declined'

  const needsRsvp = g.rsvp_status === 'pending'
  const needsHotel = !declined && Boolean(hotel) && !g.hotel_booked
  const needsFlight = !declined && !g.arrival_flight

  const daysLeft = hotel?.book_by_date ? daysUntil(hotel.book_by_date) : null
  const urgent = daysLeft !== null && daysLeft <= 45

  const tasks: TaskKey[] = [
    ...(needsRsvp ? (['rsvp'] as const) : []),
    ...(needsHotel ? (['hotel'] as const) : []),
    ...(needsFlight ? (['flight'] as const) : []),
  ]

  async function run(fn: () => Promise<unknown>, done: string) {
    setBusy(true)
    try {
      await fn()
      onToast(done)
      setOpen(null)
      onDone()
    } catch (e) {
      onToast((e as Error).message, 'plain')
    } finally {
      setBusy(false)
    }
  }

  if (tasks.length === 0) {
    return (
      <section className="todo done" aria-label="Nothing left to do">
        <span className="todo-tick" aria-hidden="true" />
        <p>
          <strong>You’re all set.</strong>{' '}
          {declined
            ? 'The couple know you can’t make it.'
            : 'Nothing left to do — just turn up.'}
        </p>
      </section>
    )
  }

  return (
    <section className="todo" aria-label="What you still need to do">
      <header className="todo-head">
        <span className="eyebrow">Your three things</span>
        <span className="todo-count">
          {tasks.length} left
        </span>
      </header>

      <ol className="todo-list">
        {needsRsvp && (
          <li className={`todo-item ${open === 'rsvp' ? 'open' : ''}`}>
            <button className="todo-row" onClick={() => setOpen(open === 'rsvp' ? null : 'rsvp')}>
              <span className="todo-n">1</span>
              <span className="todo-text">
                <b>Let Elena &amp; Matteo know if you’re coming</b>
                <small>They’re holding a seat until they hear</small>
              </span>
              <span className="todo-go" aria-hidden="true" />
            </button>
            {open === 'rsvp' && (
              <div className="todo-body">
                <div className="todo-actions">
                  <button
                    className="btn primary small"
                    disabled={busy}
                    onClick={() =>
                      run(
                        () =>
                          updateRsvp({
                            status: 'attending',
                            dietary: g.dietary,
                            bringing_plus_one: Boolean(g.plus_one_name),
                            plus_one_name: g.plus_one_name,
                            plus_one_dietary: g.plus_one_dietary,
                          }),
                        'Wonderful — you’re on the list.',
                      )
                    }
                  >
                    We’re coming
                  </button>
                  <button
                    className="btn small"
                    disabled={busy}
                    onClick={() =>
                      run(
                        () =>
                          updateRsvp({
                            status: 'declined',
                            dietary: null,
                            bringing_plus_one: false,
                            plus_one_name: null,
                            plus_one_dietary: null,
                          }),
                        'Thank you for letting them know.',
                      )
                    }
                  >
                    Can’t make it
                  </button>
                </div>
                <p className="todo-note">
                  You can add dietary needs and a plus one afterwards, in Your RSVP below.
                </p>
              </div>
            )}
          </li>
        )}

        {needsHotel && hotel && (
          <li className={`todo-item ${open === 'hotel' ? 'open' : ''} ${urgent ? 'urgent' : ''}`}>
            <button className="todo-row" onClick={() => setOpen(open === 'hotel' ? null : 'hotel')}>
              <span className="todo-n">{needsRsvp ? 2 : 1}</span>
              <span className="todo-text">
                <b>
                  Book {hotel.name.replace(/\s*\(.*\)$/, '')}
                  {hotel.book_by_date ? ` by ${longDate(hotel.book_by_date)}` : ''}
                </b>
                <small>
                  {daysLeft === null
                    ? 'The block is released once the deadline passes'
                    : daysLeft > 0
                      ? `${daysLeft} days left — the block is released after that`
                      : 'The block has been released — ask Bells what’s still free'}
                </small>
              </span>
              <span className="todo-go" aria-hidden="true" />
            </button>
            {open === 'hotel' && (
              <div className="todo-body">
                <dl className="todo-facts">
                  <div>
                    <dt>Block code</dt>
                    <dd>
                      <span className="code">{hotel.block_code ?? 'none'}</span>
                    </dd>
                  </div>
                  <div>
                    <dt>Rate</dt>
                    <dd>{hotel.nightly_rate ? `€${hotel.nightly_rate} / night` : 'not listed'}</dd>
                  </div>
                </dl>
                <div className="todo-actions">
                  {hotel.url && (
                    <a className="btn small" href={hotel.url} target="_blank" rel="noopener noreferrer">
                      Open the hotel ↗
                    </a>
                  )}
                  <button
                    className="btn primary small"
                    disabled={busy}
                    onClick={() =>
                      run(() => updateTravel({ hotel_booked: true }), 'Room booked — ticked off.')
                    }
                  >
                    I’ve booked it
                  </button>
                </div>
                <p className="todo-note">Quote the block code at checkout or it won’t apply.</p>
              </div>
            )}
          </li>
        )}

        {needsFlight && (
          <li className={`todo-item ${open === 'flight' ? 'open' : ''}`}>
            <button className="todo-row" onClick={() => setOpen(open === 'flight' ? null : 'flight')}>
              <span className="todo-n">{tasks.indexOf('flight') + 1}</span>
              <span className="todo-text">
                <b>Send us your flight so we can collect you</b>
                <small>A free shuttle meets every arrival — we just need the time</small>
              </span>
              <span className="todo-go" aria-hidden="true" />
            </button>
            {open === 'flight' && (
              <div className="todo-body">
                <div className="flight-form">
                  <label>
                    Flight
                    <input
                      value={flightNo}
                      disabled={busy}
                      placeholder="AZ 1272"
                      onChange={(e) => setFlightNo(e.target.value)}
                    />
                  </label>
                  <label>
                    Lands on
                    <input
                      type="date"
                      value={flightDate}
                      disabled={busy}
                      min="2027-06-08"
                      max="2027-06-12"
                      onChange={(e) => setFlightDate(e.target.value)}
                    />
                  </label>
                  <label>
                    At
                    <input
                      type="time"
                      value={flightTime}
                      disabled={busy}
                      onChange={(e) => setFlightTime(e.target.value)}
                    />
                  </label>
                </div>
                <div className="todo-actions">
                  <button
                    className="btn primary small"
                    disabled={busy || !flightNo.trim() || !flightDate || !flightTime}
                    onClick={() =>
                      run(
                        () =>
                          updateTravel({
                            arrival_flight: flightNo.trim(),
                            arrival_at: `${flightDate}T${flightTime}`,
                          }),
                        'Got it — your pickup is below.',
                      )
                    }
                  >
                    {busy ? 'Finding you a seat…' : 'Save and find my pickup'}
                  </button>
                </div>
                <p className="todo-note">
                  Naples (NAP). We work out the shuttle the moment you save this.
                </p>
              </div>
            )}
          </li>
        )}
      </ol>
    </section>
  )
}
