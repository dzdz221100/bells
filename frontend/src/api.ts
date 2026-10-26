import { getToken, markExpired, setSession } from './auth'
import type { SessionInfo } from './auth'
import type {
  ApproveResult,
  ChatReply,
  Dashboard,
  Escalation,
  GuestSummary,
  DraftBundle,
  HostProposal,
  HostReply,
  Impact,
  MyRegistry,
  Overview,
  ScheduleReport,
  Spend,
  Wedding,
} from './types'

/** The dev server proxies /api to FastAPI on :8000 (see vite.config.ts). */
const BASE = import.meta.env.VITE_API_BASE ?? ''

function headers(json = false): HeadersInit {
  const h: Record<string, string> = {}
  if (json) h['Content-Type'] = 'application/json'
  const token = getToken()
  if (token) h['X-Bells-Session'] = token
  return h
}

async function errorText(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body?.detail === 'string') return body.detail
    return JSON.stringify(body)
  } catch {
    return `${res.status} ${res.statusText}`
  }
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

/**
 * A 401 on a call we sent a token with means the server no longer knows that
 * session — almost always because the backend restarted, since sessions live
 * in its memory. Drop it and bounce back to sign-in with a word of
 * explanation, rather than leaving the page on blank skeletons forever.
 */
function handleExpiredSession(status: number) {
  if (status === 401 && getToken()) {
    setSession(null)
    markExpired()
    window.location.replace('/')
  }
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: headers() })
  if (!res.ok) {
    handleExpiredSession(res.status)
    throw new ApiError(await errorText(res), res.status)
  }
  return res.json() as Promise<T>
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: headers(true),
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    handleExpiredSession(res.status)
    throw new ApiError(await errorText(res), res.status)
  }
  return res.json() as Promise<T>
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: headers(true),
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    handleExpiredSession(res.status)
    throw new ApiError(await errorText(res), res.status)
  }
  return res.json() as Promise<T>
}

/* ----------------------------------------------------------------- auth */

export const getAuthOptions = () =>
  get<{ demo_mode: boolean; demo_host_passcode: string | null }>('/api/auth/options')

export const signInGuest = (email: string) =>
  post<SessionInfo>('/api/auth/guest', { email })

export const signInDemoGuest = () => post<SessionInfo>('/api/auth/guest/demo')

export const signInHost = (passcode: string) =>
  post<SessionInfo>('/api/auth/host', { passcode })

export const signOut = () => post<{ ok: boolean }>('/api/auth/signout')

export const whoami = () => get<SessionInfo>('/api/auth/me')

/* ---------------------------------------------------------------- guest */

export const getWedding = () => get<Wedding>('/api/wedding')
export const getDashboard = () => get<Dashboard>('/api/me/dashboard')
export const sendChat = (message: string) => post<ChatReply>('/api/chat', { message })

export const getRegistry = () => get<MyRegistry>('/api/me/registry')

export const updateTravel = (body: {
  hotel_booked?: boolean
  arrival_flight?: string
  arrival_at?: string
}) => put<{ ok: boolean; solved_in_ms: number | null }>('/api/me/travel', body)

export const updateRsvp = (body: {
  status: 'attending' | 'declined' | 'pending'
  dietary: string | null
  bringing_plus_one: boolean
  plus_one_name: string | null
  plus_one_dietary: string | null
}) =>
  put<{ ok: boolean; party_size: number; plus_one_name: string | null }>(
    '/api/me/rsvp',
    body,
  )
export const claimRegistryItem = (id: number) =>
  post<{ ok: boolean; item: string }>(`/api/me/registry/${id}/claim`)
export const unclaimRegistryItem = (id: number) =>
  post<{ ok: boolean; item: string }>(`/api/me/registry/${id}/unclaim`)

/* ----------------------------------------------------------------- host */

export const getEscalations = (status = 'open') =>
  get<Escalation[]>(`/api/host/escalations?status=${status}`)
export const getImpact = () => get<Impact>('/api/host/impact')
export const getOverview = () => get<Overview>('/api/host/overview')
export const getSpend = (projectionGuests = 150) =>
  get<Spend>(`/api/host/spend?projection_guests=${projectionGuests}`)
export const getShuttles = () => get<ScheduleReport>('/api/host/shuttles')
export const getGuestList = () => get<GuestSummary[]>('/api/host/guests')

/* --- the couple's concierge --- */

export const sendHostChat = (message: string) =>
  post<HostReply>('/api/host/chat', { message })

export const getProposals = () => get<HostProposal[]>('/api/host/proposals')

export const confirmProposal = (id: string) =>
  post<{ ok: boolean; kind: string; summary: string }>(`/api/host/proposals/${id}/confirm`)

export const cancelProposal = (id: string) =>
  post<{ ok: boolean }>(`/api/host/proposals/${id}/cancel`)

export const getDrafts = () => get<DraftBundle>('/api/host/drafts')

export const approveDraft = (id: string, message?: string) =>
  post<{ ok: boolean; delivered: boolean }>(`/api/host/drafts/${id}/approve`,
    message === undefined ? {} : { message })

export const skipDraft = (id: string) =>
  post<{ ok: boolean }>(`/api/host/drafts/${id}/skip`)

export const approveAllDrafts = (segment?: string) =>
  post<{ ok: boolean; approved: number }>(
    `/api/host/drafts/approve-all${segment ? `?segment=${encodeURIComponent(segment)}` : ''}`,
  )

export const approveEscalation = (id: number, answer: string, topic?: string) =>
  post<ApproveResult>(`/api/host/escalations/${id}/approve`, { answer, topic })

export const dismissEscalation = (id: number) =>
  post<{ ok: boolean }>(`/api/host/escalations/${id}/dismiss`)

export const solveShuttles = () =>
  post<{ solved_in_ms: number; previous_runs: number; report: ScheduleReport }>(
    '/api/host/shuttles/solve',
  )
