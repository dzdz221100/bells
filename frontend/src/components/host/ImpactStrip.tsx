import type { Impact } from '../../types'

type Props = {
  impact: Impact | null
  minutesPerQuestion: number
  onMinutesChange: (n: number) => void
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  )
}

export default function ImpactStrip({ impact, minutesPerQuestion, onMinutesChange }: Props) {
  const answered = impact?.answered_automatically ?? 0
  const rate = impact?.escalation_rate
  const minutesSaved = answered * minutesPerQuestion
  const hours = minutesSaved / 60

  return (
    <section className="impact">
      <div className="stats">
        <Stat
          label="Answered automatically"
          value={answered.toLocaleString()}
          sub={impact ? `of ${impact.turns.toLocaleString()} guest questions` : undefined}
        />
        <Stat
          label="Escalation rate"
          value={rate == null ? '—' : `${(rate * 100).toFixed(1)}%`}
          sub={impact ? `${impact.escalated} sent to you` : undefined}
        />
        <Stat
          label="Minutes saved"
          value={minutesSaved.toLocaleString()}
          sub={hours >= 1 ? `${hours.toFixed(1)} hours of your time` : 'of your time'}
        />
        <Stat
          label="Facts Bells knows"
          value={(impact?.facts_total ?? 0).toLocaleString()}
          sub={
            impact?.facts_from_host_console
              ? `${impact.facts_from_host_console} added from this console`
              : 'the agent answers only from these'
          }
        />
      </div>

      <div className="assumption">
        <span>
          <b>Assumption:</b> each question Bells answers saves the couple
        </span>
        <span className="assumption-field">
          <input
            type="number"
            min={0}
            max={60}
            step={0.5}
            value={minutesPerQuestion}
            aria-label="minutes saved per answered question"
            onChange={(e) => onMinutesChange(Math.max(0, Number(e.target.value) || 0))}
          />
          <span>min</span>
        </span>
        <span>
          of replying by hand — so minutes saved = {answered.toLocaleString()} answered ×{' '}
          {minutesPerQuestion} min = <b>{minutesSaved.toLocaleString()} min</b>. Change the
          figure to test it; nothing else on this page depends on it.
        </span>
      </div>
    </section>
  )
}
