import type { ScheduleReport } from '../../types'
import { clock, dayLabel, parseLocal } from '../../lib/format'

type Props = {
  report: ScheduleReport | null
  solving: boolean
  lastSolveMs: number | null
  onSolve: () => void
}

const n = (v: number) => v.toLocaleString('en-US')

function Compare({ report }: { report: ScheduleReport }) {
  const { baseline: b, solved: s, savings, assumptions: a } = report
  const rows: [string, string, string, string][] = [
    ['Airport runs', n(b.runs), n(s.runs), `−${savings.runs}`],
    ['Driver hours', b.driver_hours.toFixed(1), s.driver_hours.toFixed(1), `−${savings.driver_hours.toFixed(1)}`],
    ['Transfer cost', `€${n(b.transfer_cost_eur)}`, `€${n(s.transfer_cost_eur)}`, `−€${n(savings.transfer_cost_eur)}`],
    ['Total wait', `${n(b.total_wait_person_minutes)} min`, `${n(s.total_wait_person_minutes)} min`,
      `+${n(savings.extra_wait_person_minutes)}`],
    ['Worst wait', `${b.max_wait_minutes} min`, `${s.max_wait_minutes} min`, `limit ${a.max_wait_minutes}`],
  ]
  return (
    <div className="compare">
      <div className="compare-head">
        <span />
        <span>One per booking</span>
        <span>Solved</span>
        <span />
      </div>
      {rows.map(([label, before, after, delta]) => (
        <div className="compare-row" key={label}>
          <span className="compare-label">{label}</span>
          <span className="compare-before">{before}</span>
          <span className="compare-after">{after}</span>
          <span className={`compare-delta ${delta.startsWith('+') ? 'up' : delta.startsWith('−') ? 'down' : ''}`}>
            {delta}
          </span>
        </div>
      ))}
      <p className="compare-note">
        Assumes €{a.cost_per_transfer_eur} per private transfer and {a.minutes_per_round_trip} min
        per round trip. Runs leave {a.buffer_minutes} min after their last arrival; nobody waits
        over {a.max_wait_minutes}.
      </p>
    </div>
  )
}

export default function Shuttles({ report, solving, lastSolveMs, onSolve }: Props) {
  if (!report) return <div className="panel skeleton" style={{ height: 340 }} />

  const days = new Map<string, typeof report.runs>()
  for (const run of report.runs) {
    const key = run.depart_at.slice(0, 10)
    days.set(key, [...(days.get(key) ?? []), run])
  }

  return (
    <section className="panel shuttles">
      <header className="panel-head">
        <div>
          <h2>Shuttles</h2>
          <p>
            {report.runs.length} runs carrying {report.seats} seats across {report.bookings}{' '}
            bookings — computed, not hand-planned.
          </p>
        </div>
        <div className="panel-actions">
          {lastSolveMs != null && <span className="solve-time">solved in {lastSolveMs} ms</span>}
          <button className="btn primary" disabled={solving} onClick={onSolve}>
            {solving ? 'Solving…' : 'Re-solve'}
          </button>
        </div>
      </header>

      <div className="panel-body">
        {report.unscheduled.length > 0 && (
          <p className="notice warn">
            {report.unscheduled.length} guest(s) with an arrival time have no shuttle:{' '}
            {report.unscheduled.join(', ')}. Hit Re-solve.
          </p>
        )}

        {[...days.entries()].map(([day, runs]) => (
          <div className="timeline-day" key={day}>
            <div className="timeline-date">{dayLabel(`${day}T00:00`)}</div>
            {runs.map((run) => {
              const fill = Math.round((run.seats_taken / run.capacity) * 100)
              const first = run.first_landing ? parseLocal(run.first_landing) : null
              const last = run.last_landing ? parseLocal(run.last_landing) : null
              return (
                <div className="run" key={run.id}>
                  <div className="run-time">
                    <span className="run-clock">{clock(run.depart_at)}</span>
                    <span className="run-id">run {run.id}</span>
                  </div>

                  <div className="run-body">
                    <div className="run-bar">
                      <span style={{ width: `${fill}%` }} />
                      <em>
                        {run.seats_taken}/{run.capacity} seats
                      </em>
                    </div>

                    <div className="run-people">
                      {run.members.map((m) => (
                        <span className="person" key={m.guest_id} title={`waits ${m.wait_minutes} min`}>
                          {m.name}
                          {m.party_size > 1 && <i>+{m.party_size - 1}</i>}
                          <b>{m.arrival_flight ?? ''}</b>
                        </span>
                      ))}
                    </div>

                    <div className="run-meta">
                      {first && last && (
                        <>
                          lands {clock(run.first_landing!)}–{clock(run.last_landing!)}
                          <span className="dot">·</span>
                        </>
                      )}
                      longest wait {run.max_wait_minutes} min
                      <span className="dot">·</span>
                      {run.to_loc}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        ))}

        <Compare report={report} />
      </div>
    </section>
  )
}
