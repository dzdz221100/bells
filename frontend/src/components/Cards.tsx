import type { Dashboard } from '../types'
import { LemonMark } from './Lemons'
import { clock, dayLabel, longDate, money } from '../lib/format'

function CardHead({ label }: { label: string }) {
  return (
    <div className="card-head">
      <span className="eyebrow">{label}</span>
      <span className="card-rule" />
    </div>
  )
}

export function HotelCard({ data, currency }: { data: Dashboard; currency: string }) {
  const h = data.hotel
  return (
    <section className="card">
      <LemonMark />
      <CardHead label="Your stay" />
      {h ? (
        <>
          <h3 className="card-title">{h.name}</h3>
          {h.address && <p className="card-sub">{h.address}</p>}
          <dl>
            <div className="row">
              <dt>Rate</dt>
              <dd>{h.nightly_rate != null ? `${money(h.nightly_rate, currency)} / night` : 'not listed'}</dd>
            </div>
            <div className="row">
              <dt>Block code</dt>
              <dd>{h.block_code ? <span className="code">{h.block_code}</span> : 'none'}</dd>
            </div>
            <div className="row">
              <dt>To venue</dt>
              <dd>{h.distance_km != null ? `${h.distance_km} km` : '—'}</dd>
            </div>
          </dl>
          {h.book_by_date && (
            <p className="deadline">
              Quote the code when you book — the block is released after{' '}
              <strong>{longDate(h.book_by_date)}</strong>.
            </p>
          )}
          {h.url && (
            <p style={{ margin: '12px 0 0', fontSize: '0.86rem' }}>
              <a href={h.url} target="_blank" rel="noopener noreferrer">
                Book this hotel →
              </a>
            </p>
          )}
        </>
      ) : (
        <p className="empty">No hotel on your booking yet. Ask Bells below and it will check.</p>
      )}
    </section>
  )
}

export function ShuttleCard({ data }: { data: Dashboard }) {
  const run = data.pickup.run
  const g = data.guest
  return (
    <section className="card">
      <CardHead label="Airport pickup" />
      {run ? (
        <>
          {/* your own flight first — the pickup time only means something next to it */}
          {g.arrival_flight && (
            <p className="your-flight">
              <strong>{g.arrival_flight}</strong> lands {clock(g.arrival_at)},{' '}
              {dayLabel(g.arrival_at)}
              {data.pickup.minutes_after_landing != null && (
                <>
                  {' '}
                  · we collect you <strong>{data.pickup.minutes_after_landing} min</strong> later
                </>
              )}
            </p>
          )}
          <div className="time-big">{clock(run.depart_at)}</div>
          <div className="time-day">
            {dayLabel(run.depart_at)} · {run.from_loc}
          </div>
          <dl>
            <div className="row">
              <dt>Dropping at</dt>
              <dd>{run.to_loc}</dd>
            </div>
            <div className="row">
              <dt>Seats</dt>
              <dd>
                {run.seats_taken} of {run.capacity} taken
              </dd>
            </div>
          </dl>
          {data.pickup.be_at_pickup_by && (
            <p className="deadline">
              Be at the pickup point by <strong>{clock(data.pickup.be_at_pickup_by)}</strong>.
            </p>
          )}
        </>
      ) : (
        <p className="empty">
          {g.arrival_at
            ? 'No shuttle booked for you yet.'
            : 'Tell Bells your flight and it will find you a shuttle.'}
        </p>
      )}
    </section>
  )
}

export function RegistryCard({
  data,
  currency,
  onOpen,
}: {
  data: Dashboard
  currency: string
  onOpen?: () => void
}) {
  const r = data.registry
  const claimed = r.total - r.available
  const pct = r.total ? Math.round((claimed / r.total) * 100) : 0
  return (
    <section className="card">
      <LemonMark />
      <CardHead label="Gift registry" />
      <h3 className="card-title">
        {r.available} of {r.total} still available
      </h3>
      <div className="meter" role="img" aria-label={`${pct}% of the registry claimed`}>
        <span style={{ width: `${pct}%` }} />
      </div>
      <p className="card-sub" style={{ fontSize: '0.82rem' }}>
        The registry is anonymous — nobody sees who chose what.
      </p>
      {r.yours.length > 0 ? (
        <ul className="yours">
          {r.yours.map((i) => (
            <li key={i.id}>
              {i.item} · {money(i.price, currency)}
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty" style={{ marginTop: 10 }}>
          You haven’t chosen a gift yet.
        </p>
      )}
      {onOpen && (
        <p style={{ margin: '14px 0 0', fontSize: '0.86rem' }}>
          <button className="linkish" onClick={onOpen}>
            Open the registry →
          </button>
        </p>
      )}
    </section>
  )
}
