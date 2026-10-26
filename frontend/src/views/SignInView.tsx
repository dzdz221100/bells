import { useEffect, useState } from 'react'
import { getAuthOptions, getWedding, signInDemoGuest, signInGuest, signInHost } from '../api'
import BellsLogo from '../components/BellsLogo'
import { LemonBranch } from '../components/Lemons'
import { takeExpiredFlag, type SessionInfo } from '../auth'
import type { Wedding } from '../types'
import { parseLocal } from '../lib/format'

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

type Props = {
  initialRole?: 'guest' | 'host'
  onSignedIn: (s: SessionInfo) => void
}

export default function SignInView({ initialRole = 'guest', onSignedIn }: Props) {
  const [role, setRole] = useState<'guest' | 'host'>(initialRole)
  const [email, setEmail] = useState('')
  const [passcode, setPasscode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [wedding, setWedding] = useState<Wedding | null>(null)
  const [demo, setDemo] = useState<{ demo_mode: boolean; demo_host_passcode: string | null } | null>(null)
  // read once on mount, so the notice does not reappear on every re-render
  const [expired] = useState(takeExpiredFlag)

  useEffect(() => {
    getWedding().then(setWedding).catch(() => {})
    getAuthOptions().then(setDemo).catch(() => {})
  }, [])

  useEffect(() => setRole(initialRole), [initialRole])

  async function run(fn: () => Promise<SessionInfo>) {
    setBusy(true)
    setError(null)
    try {
      onSignedIn(await fn())
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const d = wedding ? parseLocal(wedding.date) : null
  const [first, second] = (wedding?.couple_names ?? ' & ').split(/\s*&\s*/)

  return (
    <div className="signin-page">
      <div className="signin-card">
        <LemonBranch className="top-left" width={150} />
        <LemonBranch className="bottom-right" width={130} />

        <div className="signin-inner">
        <div className="signin-brand">
          <BellsLogo size="lg" ringOnHover />
        </div>
        <div className="signin-wordmark">Bells</div>

        <h1 className="signin-names">
          <span className="hero-name">{first}</span>{' '}
          <span className="hero-amp">&amp;</span>{' '}
          <span className="hero-name">{second}</span>
        </h1>
        {wedding && d && (
          <p className="signin-meta">
            {d.getDate()} {MONTHS[d.getMonth()]} {d.getFullYear()}
            <span className="hero-dot">✦</span>
            {wedding.city}
            <span className="hero-dot">✦</span>
            {wedding.country}
          </p>
        )}

        <div className="role-switch" role="tablist" aria-label="Sign in as">
          <button
            role="tab"
            aria-selected={role === 'guest'}
            className={role === 'guest' ? 'on' : ''}
            onClick={() => {
              setRole('guest')
              setError(null)
            }}
          >
            I’m a guest
          </button>
          <button
            role="tab"
            aria-selected={role === 'host'}
            className={role === 'host' ? 'on' : ''}
            onClick={() => {
              setRole('host')
              setError(null)
            }}
          >
            We’re the couple
          </button>
        </div>

        {role === 'guest' ? (
          <form
            className="signin-form"
            onSubmit={(e) => {
              e.preventDefault()
              if (email.trim()) run(() => signInGuest(email.trim()))
            }}
          >
            <label htmlFor="email">The email your invitation went to</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              disabled={busy}
              onChange={(e) => setEmail(e.target.value)}
            />
            <button className="btn primary wide" type="submit" disabled={busy || !email.trim()}>
              {busy ? 'Checking…' : 'Open my wedding page'}
            </button>
            {demo?.demo_mode && (
              <button
                type="button"
                className="btn ghost wide"
                disabled={busy}
                onClick={() => run(signInDemoGuest)}
              >
                Just show me — sign in as a random guest
              </button>
            )}
          </form>
        ) : (
          <form
            className="signin-form"
            onSubmit={(e) => {
              e.preventDefault()
              if (passcode.trim()) run(() => signInHost(passcode.trim()))
            }}
          >
            <label htmlFor="passcode">Host passcode</label>
            <input
              id="passcode"
              type="password"
              autoComplete="current-password"
              placeholder="••••••"
              value={passcode}
              disabled={busy}
              onChange={(e) => setPasscode(e.target.value)}
            />
            <button className="btn primary wide" type="submit" disabled={busy || !passcode.trim()}>
              {busy ? 'Checking…' : 'Open the host console'}
            </button>
            {demo?.demo_host_passcode && (
              <p className="signin-hint">
                Demo passcode: <span className="code">{demo.demo_host_passcode}</span>. Set{' '}
                <span className="code">BELLS_HOST_PASSCODE</span> in <span className="code">.env</span>{' '}
                to change it — this hint disappears once you do.
              </p>
            )}
          </form>
        )}

        {expired && !error && (
          <p className="signin-hint">Your session expired — open your page again.</p>
        )}

        {error && <p className="signin-error">{error}</p>}

        <p className="signin-foot">
          Guests see only their own booking. The guest list is visible to the couple only.
        </p>
        </div>
      </div>
    </div>
  )
}
