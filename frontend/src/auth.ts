export type SessionInfo = {
  token: string
  role: 'guest' | 'host'
  guest: { id: number; name: string; language: string } | null
}

const KEY = 'bells.session'
const EXPIRED_KEY = 'bells.expired'

let current: SessionInfo | null = null

export function loadSession(): SessionInfo | null {
  if (current) return current
  try {
    const raw = localStorage.getItem(KEY)
    current = raw ? (JSON.parse(raw) as SessionInfo) : null
  } catch {
    current = null
  }
  return current
}

export function setSession(s: SessionInfo | null) {
  current = s
  if (s) localStorage.setItem(KEY, JSON.stringify(s))
  else localStorage.removeItem(KEY)
}

/** Sent as X-Bells-Session on every API call. Sessions live in the server's memory. */
export const getToken = () => loadSession()?.token ?? null

/**
 * Sessions live in the backend's memory, so restarting it invalidates every
 * token. When that happens mid-visit we drop the session and flag it, so the
 * sign-in screen can explain rather than just appearing.
 */
export function markExpired() {
  try {
    sessionStorage.setItem(EXPIRED_KEY, '1')
  } catch {
    /* private browsing — the flag is a nicety, not a requirement */
  }
}

/** True once, then forgotten: the message shows on the next sign-in only. */
export function takeExpiredFlag(): boolean {
  try {
    const had = sessionStorage.getItem(EXPIRED_KEY) === '1'
    if (had) sessionStorage.removeItem(EXPIRED_KEY)
    return had
  } catch {
    return false
  }
}
