import { useEffect, useState } from 'react'
import { updateRsvp } from '../api'
import type { Dashboard } from '../types'

type Props = {
  data: Dashboard
  onSaved: () => void
  onToast: (text: string, tone?: 'ok' | 'plain') => void
}

const DIETS = ['Vegetarian', 'Vegan', 'Gluten-free', 'Dairy-free', 'No nuts', 'No shellfish', 'No pork']

function DietPicker({
  value,
  onChange,
  disabled,
  placeholder,
}: {
  value: string
  onChange: (v: string) => void
  disabled: boolean
  placeholder: string
}) {
  const parts = value.split(',').map((d) => d.trim()).filter(Boolean)
  const has = (d: string) => parts.some((p) => p.toLowerCase() === d.toLowerCase())
  const toggle = (d: string) =>
    onChange(
      (has(d) ? parts.filter((p) => p.toLowerCase() !== d.toLowerCase()) : [...parts, d]).join(', '),
    )

  return (
    <div className="diet-picker">
      <div className="diet-chips">
        {DIETS.map((d) => (
          <button
            key={d}
            type="button"
            className={`chip ${has(d) ? 'on' : ''}`}
            disabled={disabled}
            onClick={() => toggle(d)}
          >
            {d}
          </button>
        ))}
      </div>
      <input
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

/**
 * Compact RSVP. Coming or not up top; everything else only unfolds once the
 * answer is yes, so a guest who can't come sees two buttons and nothing more.
 *
 * The plus one is explicit — name and dietary needs — rather than a headcount,
 * because "2" tells the caterer and the seating plan nothing useful.
 */
export default function RsvpCard({ data, onSaved, onToast }: Props) {
  const g = data.guest
  const [status, setStatus] = useState(g.rsvp_status)
  const [diet, setDiet] = useState(g.dietary ?? '')
  const [bringing, setBringing] = useState(Boolean(g.plus_one_name))
  const [p1Name, setP1Name] = useState(g.plus_one_name ?? '')
  const [p1Diet, setP1Diet] = useState(g.plus_one_dietary ?? '')
  const [open, setOpen] = useState(g.rsvp_status === 'pending')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setStatus(g.rsvp_status)
    setDiet(g.dietary ?? '')
    setBringing(Boolean(g.plus_one_name))
    setP1Name(g.plus_one_name ?? '')
    setP1Diet(g.plus_one_dietary ?? '')
  }, [g.rsvp_status, g.dietary, g.plus_one_name, g.plus_one_dietary])

  const dirty =
    status !== g.rsvp_status ||
    diet !== (g.dietary ?? '') ||
    bringing !== Boolean(g.plus_one_name) ||
    p1Name !== (g.plus_one_name ?? '') ||
    p1Diet !== (g.plus_one_dietary ?? '')

  async function save(next = status) {
    setSaving(true)
    try {
      const res = await updateRsvp({
        status: next,
        dietary: diet || null,
        bringing_plus_one: bringing,
        plus_one_name: p1Name || null,
        plus_one_dietary: p1Diet || null,
      })
      onToast(
        next === 'declined'
          ? 'Thank you for letting them know.'
          : res.plus_one_name
            ? `Lovely — you and ${res.plus_one_name} are on the list.`
            : 'Lovely — you’re on the list.',
      )
      if (next !== 'pending') setOpen(false)
      onSaved()
    } catch (e) {
      onToast((e as Error).message, 'plain')
    } finally {
      setSaving(false)
    }
  }

  const going = status === 'attending'
  const seats = going ? 1 + (bringing && p1Name.trim() ? 1 : 0) : 0

  // collapsed summary once they've answered
  if (!open) {
    return (
      <section className={`rsvp-strip ${status}`}>
        <span className="rsvp-state">
          <i aria-hidden="true" />
          {going
            ? g.plus_one_name
              ? `You and ${g.plus_one_name} are coming`
              : 'You’re coming'
            : 'You’ve said you can’t make it'}
        </span>
        {going && (
          <span className="rsvp-sub">
            {g.dietary || g.plus_one_dietary
              ? [g.dietary, g.plus_one_dietary].filter(Boolean).join(' · ')
              : 'No dietary needs noted'}
          </span>
        )}
        <button className="btn ghost small" onClick={() => setOpen(true)}>
          {going ? 'Change' : 'Changed your mind?'}
        </button>
      </section>
    )
  }

  return (
    <section className={`rsvp-strip open ${status}`}>
      <div className="rsvp-ask">
        <span className="eyebrow">{status === 'declined' ? 'Changed your mind?' : 'Your RSVP'}</span>
        <div className="rsvp-choice">
          <button
            className={`rsvp-btn yes ${going ? 'on' : ''}`}
            disabled={saving}
            onClick={() => {
              setStatus('attending')
              if (g.rsvp_status !== 'attending') setDiet(g.dietary ?? '')
            }}
          >
            We’re coming
          </button>
          <button
            className={`rsvp-btn no ${status === 'declined' ? 'on' : ''}`}
            disabled={saving}
            onClick={() => {
              setStatus('declined')
              save('declined')
            }}
          >
            Can’t make it
          </button>
        </div>
      </div>

      {going && (
        <div className="rsvp-detail">
          <div className="rsvp-field">
            <label>Anything you can’t eat?</label>
            <DietPicker
              value={diet}
              onChange={setDiet}
              disabled={saving}
              placeholder="Or type it — the caterer reads this"
            />
          </div>

          {g.plus_one_allowed ? (
            <div className="rsvp-field">
              <label className="with-switch">
                Bringing a plus one?
                <button
                  type="button"
                  role="switch"
                  aria-checked={bringing}
                  className={`switch ${bringing ? 'on' : ''}`}
                  disabled={saving}
                  onClick={() => setBringing((b) => !b)}
                >
                  <span />
                </button>
              </label>

              {bringing ? (
                <>
                  <input
                    className="p1-name"
                    value={p1Name}
                    disabled={saving}
                    placeholder="Their name — needed for the seating plan"
                    onChange={(e) => setP1Name(e.target.value)}
                  />
                  {p1Name.trim() && (
                    <DietPicker
                      value={p1Diet}
                      onChange={setP1Diet}
                      disabled={saving}
                      placeholder={`Anything ${p1Name.trim().split(' ')[0]} can’t eat?`}
                    />
                  )}
                </>
              ) : (
                <p className="rsvp-hint">
                  Your invitation says “and guest” — tell the couple who by 1 May.
                </p>
              )}
            </div>
          ) : (
            <p className="rsvp-hint solo">
              Your invitation is for you alone. Message Bells if that’s changed.
            </p>
          )}
        </div>
      )}

      {going && (
        <div className="rsvp-save">
          <span className="rsvp-seats">
            {seats} {seats === 1 ? 'seat' : 'seats'} at the table
          </span>
          <button
            className="btn primary small"
            disabled={saving || (bringing && !p1Name.trim())}
            onClick={() => save()}
          >
            {saving ? 'Saving…' : dirty ? 'Save my RSVP' : 'Saved'}
          </button>
          {g.rsvp_status !== 'pending' && (
            <button className="btn ghost small" disabled={saving} onClick={() => setOpen(false)}>
              Close
            </button>
          )}
        </div>
      )}
    </section>
  )
}
