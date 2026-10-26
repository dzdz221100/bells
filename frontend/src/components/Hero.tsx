import { useEffect, useState } from 'react'
import type { Wedding } from '../types'
import { parseLocal } from '../lib/format'
import { LemonBranch } from './Lemons'

const pad = (n: number) => String(n).padStart(2, '0')

function useCountdown(target: Date | null) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  if (!target) return null
  const diff = target.getTime() - now
  if (diff <= 0) return null
  return {
    days: Math.floor(diff / 86_400_000),
    hours: Math.floor(diff / 3_600_000) % 24,
    minutes: Math.floor(diff / 60_000) % 60,
    seconds: Math.floor(diff / 1000) % 60,
  }
}

export default function Hero({ wedding }: { wedding: Wedding }) {
  // ceremony day; the exact hour is a wedding_fact, so the countdown runs to midnight
  const target = parseLocal(wedding.date)
  const left = useCountdown(target)
  const [first, second] = wedding.couple_names.split(/\s*&\s*/)
  const d = target

  return (
    <header className="hero">
      {/* the coast at the foot of the card, dissolving up into the paper —
          the type always sits on white, never on the photograph */}
      <picture className="hero-photo">
        <source media="(max-width: 700px)" srcSet="/hero/amalfi.webp" />
        <img src="/hero/amalfi-wide.webp" alt="" aria-hidden="true" loading="eager" />
      </picture>

      {/* a branch into each opposite corner, as on the invitation */}
      <LemonBranch className="top-left" width={200} />
      <LemonBranch className="bottom-right" width={170} />

      <div className="hero-inner">
        {/* real spaces around the ampersand: without them the whole line is a
            single unbreakable token and a narrow screen splits it mid-name */}
        <h1 className="hero-names">
          <span className="hero-name">{first}</span>{' '}
          <span className="hero-amp">&amp;</span>{' '}
          <span className="hero-name">{second}</span>
        </h1>
        <div className="hero-rule" aria-hidden="true" />
        <p className="hero-meta">
          {d && `${pad(d.getDate())} · ${pad(d.getMonth() + 1)} · ${d.getFullYear()}`}
          <span className="hero-dot">—</span>
          {wedding.city.split(',')[0].toUpperCase()}
          <span className="hero-dot">—</span>
          ITALIA
        </p>

      {left ? (
        <div className="countdown" aria-label="time until the wedding">
          {([
            ['days', left.days],
            ['hours', left.hours],
            ['minutes', left.minutes],
            ['seconds', left.seconds],
          ] as const).map(([label, value]) => (
            <div className="count-cell" key={label}>
              <div className="count-num">
                {/* keyed by the value: React remounts it, so the CSS tick
                    animation replays on every change. Presentation only. */}
                <span key={value}>
                  {label === 'days' ? value : String(value).padStart(2, '0')}
                </span>
              </div>
              <div className="count-label">{label}</div>
            </div>
          ))}
        </div>
      ) : (
        <p className="countdown-past">The day is here.</p>
      )}
      </div>
    </header>
  )
}
