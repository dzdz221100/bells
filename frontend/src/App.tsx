import { useCallback, useEffect, useState } from 'react'
import { signOut } from './api'
import { loadSession, setSession, type SessionInfo } from './auth'
import BellsLogo from './components/BellsLogo'
import GuestView from './views/GuestView'
import HostView from './views/HostView'
import RegistryView from './views/RegistryView'
import SignInView from './views/SignInView'

/**
 * Two views, one bundle: / for guests, /host for the couple, and a sign-in
 * screen in front of both. A router library would be one more dependency for
 * one more route.
 */
export default function App() {
  const [path, setPath] = useState(window.location.pathname)
  const [session, setSessionState] = useState<SessionInfo | null>(() => loadSession())

  useEffect(() => {
    const onPop = () => setPath(window.location.pathname)
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const wantsHost = path.startsWith('/host')
  const wantsRegistry = path.startsWith('/registry')

  const onSignedIn = useCallback((s: SessionInfo) => {
    setSession(s)
    setSessionState(s)
    navigate(s.role === 'host' ? '/host' : '/')
  }, [])

  const leave = useCallback(async (to: string) => {
    try {
      await signOut()
    } catch {
      /* the session may already be gone server-side; clear it locally anyway */
    }
    setSession(null)
    setSessionState(null)
    navigate(to)
  }, [])

  if (!session || (wantsHost && session.role !== 'host') || (!wantsHost && session.role !== 'guest')) {
    // Signed in as the wrong role for this page: ask again, preselecting the
    // tab for the page they asked for.
    return (
      <SignInView
        initialRole={wantsHost ? 'host' : 'guest'}
        onSignedIn={onSignedIn}
      />
    )
  }

  if (session.role === 'host') {
    return <HostView onSignOut={() => leave('/host')} />
  }

  return wantsRegistry ? (
    <div className="page">
      <GuestChrome session={session} onSignOut={() => leave('/')} active="registry" />
      <RegistryView onBack={() => navigate('/')} />
    </div>
  ) : (
    <GuestView
      session={session}
      onSignOut={() => leave('/')}
      onOpenRegistry={() => navigate('/registry')}
    />
  )
}

/** The shared guest top bar, so the registry page carries the same chrome. */
function GuestChrome({
  session,
  onSignOut,
  active,
}: {
  session: SessionInfo
  onSignOut: () => void
  active: 'wedding' | 'registry'
}) {
  return (
    <div className="topbar">
      <div className="brand">
        <BellsLogo />
        <span className="brand-name">Bells</span>
      </div>
      <div className="whoami">
        <nav className="tabs">
          <button
            className={`tab ${active === 'wedding' ? 'on' : ''}`}
            onClick={() => navigate('/')}
          >
            Wedding
          </button>
          <button
            className={`tab ${active === 'registry' ? 'on' : ''}`}
            aria-current={active === 'registry' ? 'page' : undefined}
          >
            Gift registry
          </button>
        </nav>
        <span className="whoami-name">{session.guest?.name}</span>
        <button className="btn ghost" onClick={onSignOut}>
          Sign out
        </button>
      </div>
    </div>
  )
}

/** Navigate without a full page load. */
export function navigate(to: string) {
  window.history.pushState({}, '', to)
  window.dispatchEvent(new PopStateEvent('popstate'))
}
