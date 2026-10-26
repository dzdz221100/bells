import type { Overview } from '../../types'
import { languageName } from '../../lib/format'

const n = (v: number) => v.toLocaleString('en-US')

function Bar({ parts }: { parts: { label: string; value: number; cls: string }[] }) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1
  return (
    <div className="rsvp-bar" role="img" aria-label={parts.map((p) => `${p.value} ${p.label}`).join(', ')}>
      {parts.map((p) => (
        <span key={p.label} className={p.cls} style={{ width: `${(p.value / total) * 100}%` }} />
      ))}
    </div>
  )
}

export default function OverviewPanel({ data }: { data: Overview | null }) {
  if (!data) return <div className="panel skeleton" style={{ height: 300 }} />

  const r = data.rsvp
  return (
    <section className="panel overview">
      <header className="panel-head">
        <div>
          <h2>Guest list</h2>
          <p>
            {n(r.attending)} of {n(data.invited)} invitations answered yes —{' '}
            <b>{n(data.seats.attending)} people</b> at the tables.
          </p>
        </div>
        <span className="count-pill">
          {r.response_rate == null ? '—' : `${Math.round(r.response_rate * 100)}% replied`}
        </span>
      </header>

      <div className="panel-body">
        <Bar
          parts={[
            { label: 'attending', value: r.attending, cls: 'yes' },
            { label: 'declined', value: r.declined, cls: 'no' },
            { label: 'still waiting', value: r.pending, cls: 'wait' },
          ]}
        />
        <div className="rsvp-key">
          <span>
            <i className="key yes" /> {n(r.attending)} attending
          </span>
          <span>
            <i className="key no" /> {n(r.declined)} declined
          </span>
          <span>
            <i className="key wait" /> {n(r.pending)} no reply
          </span>
        </div>

        <div className="ov-grid">
          <div className="ov-block">
            <h4>Catering</h4>
            {data.dietary.length === 0 ? (
              <p className="empty">No dietary needs recorded yet.</p>
            ) : (
              <ul className="ov-list">
                {data.dietary.map((d) => (
                  <li key={d.need}>
                    <span>{d.need}</span>
                    <b>{d.people}</b>
                  </li>
                ))}
              </ul>
            )}
            <p className="ov-note">
              {n(data.dietary_people)} of {n(data.seats.attending)} people need a special plate.
            </p>
          </div>

          <div className="ov-block">
            <h4>Beds</h4>
            {data.beds.length === 0 ? (
              <p className="empty">Nobody has a hotel yet.</p>
            ) : (
              <ul className="ov-list">
                {data.beds.map((b) => (
                  <li key={b.hotel}>
                    <span>{b.hotel}</span>
                    <b>{b.people}</b>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="ov-block">
            <h4>Plus ones</h4>
            <ul className="ov-list">
              <li>
                <span>Named</span>
                <b>{data.plus_ones.named}</b>
              </li>
              <li className={data.plus_ones.unnamed ? 'warn' : ''}>
                <span>Invited, not named</span>
                <b>{data.plus_ones.unnamed}</b>
              </li>
              <li>
                <span>Invitations with “and guest”</span>
                <b>{data.plus_ones.invited}</b>
              </li>
            </ul>
            <p className="ov-note">
              An unnamed plus one has no seat on the shuttles and no plate.
            </p>
          </div>

          <div className="ov-block">
            <h4>Travel</h4>
            <ul className="ov-list">
              <li>
                <span>Flights told to us</span>
                <b>{data.travel.with_flights}</b>
              </li>
              <li>
                <span>On a shuttle</span>
                <b>{data.travel.on_a_shuttle}</b>
              </li>
              <li className={data.travel.no_shuttle_yet ? 'warn' : ''}>
                <span>Waiting for a seat</span>
                <b>{data.travel.no_shuttle_yet}</b>
              </li>
            </ul>
          </div>

          <div className="ov-block">
            <h4>Languages</h4>
            <ul className="ov-list">
              {data.languages.map((l) => (
                <li key={l.code}>
                  <span>{languageName(l.code)}</span>
                  <b>{l.guests}</b>
                </li>
              ))}
            </ul>
            <p className="ov-note">Bells replies in whichever one a guest writes in.</p>
          </div>
        </div>

        {r.pending > 0 && (
          <p className="notice">
            <b>{r.pending}</b> {r.pending === 1 ? 'guest has' : 'guests have'} not replied, which is{' '}
            up to <b>{n(data.seats.pending)}</b> more seats, meals and shuttle places. The caterer
            takes final numbers on 29 May.
          </p>
        )}
      </div>
    </section>
  )
}
