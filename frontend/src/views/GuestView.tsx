import { useCallback, useEffect, useMemo, useState } from 'react'
import { getDashboard, getWedding, sendChat } from '../api'
import type { SessionInfo } from '../auth'
import BellsLogo from '../components/BellsLogo'
import Chat from '../components/Chat'
import Hero from '../components/Hero'
import NotComingCard from '../components/NotComingCard'
import RsvpCard from '../components/RsvpCard'
import ShuttleTimeline from '../components/ShuttleTimeline'
import ThreeThings from '../components/ThreeThings'
import { LemonGarland } from '../components/Lemons'
import Toast, { type ToastState } from '../components/host/Toast'
import { HotelCard, RegistryCard } from '../components/Cards'
import type { ChatMessage, Dashboard, Wedding } from '../types'
import { daysUntil } from '../lib/format'

/** The app speaks English; Bells answers in whatever language you write in. */
const GREETING =
  'Hello {name} — I’m Bells, your concierge for the wedding. Ask me anything, ' +
  'in any language.'

const greetingFor = (name: string) => GREETING.replace('{name}', name.split(' ')[0])

/**
 * Chips that know where the guest is standing.
 *
 * Before they've booked, booking is the live question; a week out from their
 * flight, the pickup is. After a reply, the chips become follow-ups to what
 * was just said rather than repeating the opening four.
 */
function suggestionsFor(dash: Dashboard | null, lastAnswer: string | null): string[] {
  if (!dash) return []
  const g = dash.guest

  if (lastAnswer) {
    const a = lastAnswer.toLowerCase()
    if (/hotel|block|palazzo|rufolo|villa romana|book/.test(a))
      return ['What’s the block code again?', 'How far is it from the venue?', 'Can I check in early?']
    if (/shuttle|pickup|airport|naples/.test(a))
      return ['What if my flight is late?', 'Can I bring a big suitcase?', 'How long is the drive?']
    if (/dress|wear|formal|shoes/.test(a))
      return ['Is it the same for the welcome dinner?', 'What colours should I avoid?']
    if (/registry|gift|present/.test(a))
      return ['Where do I ship it?', 'Is a cash gift normal here?']
    if (/ceremony|terrace|cimbrone/.test(a))
      return ['How do I get to the venue?', 'What time does dinner start?', 'Is it unplugged?']
    return ['What else should I know?', 'What’s happening on Friday?', 'What’s the dress code?']
  }

  const chips: string[] = []
  if (dash.hotel && !g.hotel_booked) chips.push('How do I book the hotel block?')
  if (!g.arrival_flight) chips.push('How do I get there from Naples?')
  const soon = g.arrival_at ? daysUntil(g.arrival_at) : null
  if (soon !== null && soon <= 7) chips.unshift('When is my pickup?')
  chips.push('What time is the ceremony?', 'What should I wear?')
  if (chips.length < 4) chips.push('What’s left on the registry?')
  return chips.slice(0, 4)
}

let toastSeq = 0
let nextId = 0
const newId = () => `m${nextId++}`

type Props = {
  session: SessionInfo
  onSignOut: () => void
  onOpenRegistry: () => void
}

export default function GuestView({ session, onSignOut, onOpenRegistry }: Props) {
  const [wedding, setWedding] = useState<Wedding | null>(null)
  const [dash, setDash] = useState<Dashboard | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [busy, setBusy] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [toast, setToast] = useState<ToastState>(null)
  const [sheetOpen, setSheetOpen] = useState(false)

  const say = (text: string, tone: 'ok' | 'plain' = 'ok') =>
    setToast({ id: ++toastSeq, text, tone })

  const refresh = useCallback(() => getDashboard().then(setDash).catch(() => {}), [])

  useEffect(() => {
    getWedding().then(setWedding).catch((e: Error) => setLoadError(e.message))
  }, [])

  // this guest's own page — the backend reads the id from the session
  useEffect(() => {
    let cancelled = false
    getDashboard()
      .then((d) => {
        if (cancelled) return
        setDash(d)
        setMessages([{ id: newId(), role: 'assistant', content: greetingFor(d.guest.name) }])
      })
      .catch((e: Error) => !cancelled && setLoadError(e.message))
    return () => {
      cancelled = true
    }
  }, [session.token])

  const send = useCallback(async (text: string) => {
    setMessages((prev) => [...prev, { id: newId(), role: 'user', content: text }])
    setBusy(true)
    try {
      const reply = await sendChat(text)
      setMessages((prev) => [
        ...prev,
        { id: newId(), role: 'assistant', content: reply.answer, reply },
      ])
      // a claim or an escalation can change the page underneath
      getDashboard().then(setDash).catch(() => {})
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { id: newId(), role: 'error', content: (e as Error).message },
      ])
    } finally {
      setBusy(false)
    }
  }, [])

  const lastAnswer = useMemo(() => {
    const answered = [...messages].reverse().find((m) => m.role === 'assistant' && m.reply)
    return answered?.content ?? null
  }, [messages])

  const suggestions = useMemo(() => suggestionsFor(dash, lastAnswer), [dash, lastAnswer])

  if (loadError && !wedding) {
    return (
      <div className="page">
        <div className="card" style={{ marginTop: 60 }}>
          <h2 className="card-title">The backend isn’t answering</h2>
          <p className="card-sub">{loadError}</p>
          <p className="card-sub" style={{ marginTop: 10 }}>
            Start it with <span className="code">backend/.venv/bin/uvicorn main:app --port 8000</span>{' '}
            from the <span className="code">backend</span> folder.
          </p>
        </div>
      </div>
    )
  }

  const declined = dash?.guest.rsvp_status === 'declined'
  const firstName = dash?.guest.name.split(' ')[0] ?? session.guest?.name.split(' ')[0] ?? 'You'

  return (
    <div className="page guest">
      <div className="topbar">
        <div className="brand">
          <BellsLogo />
          <span className="brand-name">Bells</span>
        </div>
        <div className="whoami">
          <nav className="tabs">
            <button className="tab on" aria-current="page">
              Wedding
            </button>
            <button className="tab" onClick={onOpenRegistry}>
              Gift registry
              {dash && dash.registry.available > 0 && (
                <span className="tab-count">{dash.registry.available}</span>
              )}
            </button>
          </nav>
          <span className="whoami-name">{dash?.guest.name ?? session.guest?.name}</span>
          <button className="btn ghost" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </div>

      {wedding ? (
        <Hero wedding={wedding} />
      ) : (
        <div className="skeleton" style={{ height: 300, marginBottom: 24 }} />
      )}

      <div className="guest-shell">
        <main className="guest-main">
          {/* the first thing on the page: what this guest still owes */}
          {dash && <ThreeThings data={dash} onDone={refresh} onToast={say} />}

          <div className={`cards ${declined ? 'two' : ''}`}>
            {dash && wedding ? (
              declined ? (
                <>
                  <NotComingCard data={dash} />
                  <RegistryCard data={dash} currency={wedding.currency} onOpen={onOpenRegistry} />
                </>
              ) : (
                <>
                  <ShuttleTimeline data={dash} />
                  <HotelCard data={dash} currency={wedding.currency} />
                  <RegistryCard data={dash} currency={wedding.currency} onOpen={onOpenRegistry} />
                </>
              )
            ) : (
              [0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 220 }} />)
            )}
          </div>

          {/* shown even when they've declined — people change their minds */}
          {dash && <RsvpCard data={dash} onSaved={refresh} onToast={say} />}

          <footer className="foot">
            <LemonGarland className="lemon-divider" />
            Bells · a concierge for {wedding?.couple_names ?? 'the couple'}’s guests
          </footer>
        </main>

        {/* Desktop: a column that stays put while the page scrolls.
            Mobile: the same markup, as a sheet over the page. */}
        <aside className={`concierge ${sheetOpen ? 'open' : ''}`}>
          <Chat
            messages={messages}
            busy={busy}
            guestName={firstName}
            suggestions={suggestions}
            onSend={send}
            compact
            onClose={() => setSheetOpen(false)}
          />
        </aside>
      </div>

      {/* Mobile: the concierge is never more than one tap away. */}
      <button
        className={`ask-bar ${sheetOpen ? 'hidden' : ''}`}
        onClick={() => setSheetOpen(true)}
      >
        <span className="ask-bell" aria-hidden="true" />
        Ask Bells anything
        {busy && <span className="ask-busy" aria-hidden="true" />}
      </button>
      <div
        className={`sheet-scrim ${sheetOpen ? 'on' : ''}`}
        onClick={() => setSheetOpen(false)}
        aria-hidden="true"
      />

      <Toast toast={toast} onDone={() => setToast(null)} />
    </div>
  )
}
