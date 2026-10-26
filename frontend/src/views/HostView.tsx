import { useCallback, useEffect, useState } from 'react'
import {
  approveEscalation,
  dismissEscalation,
  getEscalations,
  getImpact,
  getOverview,
  getDrafts,
  getShuttles,
  getSpend,
  getWedding,
  solveShuttles,
} from '../api'
import BellsLogo from '../components/BellsLogo'
import HostChat from '../components/host/HostChat'
import ImpactStrip from '../components/host/ImpactStrip'
import Messages from '../components/host/Messages'
import OverviewPanel from '../components/host/Overview'
import Inbox from '../components/host/Inbox'
import Shuttles from '../components/host/Shuttles'
import SpendPanel from '../components/host/SpendPanel'
import Toast, { type ToastState } from '../components/host/Toast'
import type { DraftBundle, Escalation, Impact, Overview, ScheduleReport, Spend, Wedding } from '../types'

let toastSeq = 0

type Props = {
  onSignOut: () => void
}

export default function HostView({ onSignOut }: Props) {
  const [wedding, setWedding] = useState<Wedding | null>(null)
  const [escalations, setEscalations] = useState<Escalation[]>([])
  const [impact, setImpact] = useState<Impact | null>(null)
  const [spend, setSpend] = useState<Spend | null>(null)
  const [shuttles, setShuttles] = useState<ScheduleReport | null>(null)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [drafts, setDrafts] = useState<DraftBundle | null>(null)

  const [loadingInbox, setLoadingInbox] = useState(true)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [solving, setSolving] = useState(false)
  const [lastSolveMs, setLastSolveMs] = useState<number | null>(null)
  const [minutes, setMinutes] = useState(3)
  const [toast, setToast] = useState<ToastState>(null)
  const [error, setError] = useState<string | null>(null)

  const say = (text: string, tone: 'ok' | 'plain' = 'ok') =>
    setToast({ id: ++toastSeq, text, tone })

  const refresh = useCallback(async () => {
    try {
      const [esc, imp, sp, ov, dr] = await Promise.all([
        getEscalations('open'), getImpact(), getSpend(150), getOverview(), getDrafts(),
      ])
      setEscalations(esc)
      setImpact(imp)
      setSpend(sp)
      setOverview(ov)
      setDrafts(dr)
      setMinutes((m) => m || imp.default_minutes_per_question)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoadingInbox(false)
    }
  }, [])

  useEffect(() => {
    getWedding().then(setWedding).catch((e: Error) => setError(e.message))
    getShuttles().then(setShuttles).catch((e: Error) => setError(e.message))

    refresh()
  }, [refresh])

  async function onApprove(e: Escalation, answer: string) {
    setBusyId(e.id)
    try {
      const res = await approveEscalation(e.id, answer)
      setEscalations((prev) => prev.filter((x) => x.id !== e.id))
      say(`Bells will answer this itself from now on — saved as “${res.topic}”.`)
      refresh()
    } catch (err) {
      say((err as Error).message, 'plain')
    } finally {
      setBusyId(null)
    }
  }

  async function onDismiss(e: Escalation) {
    setBusyId(e.id)
    try {
      await dismissEscalation(e.id)
      setEscalations((prev) => prev.filter((x) => x.id !== e.id))
      say('Dismissed — Bells will keep escalating this one.', 'plain')
      refresh()
    } catch (err) {
      say((err as Error).message, 'plain')
    } finally {
      setBusyId(null)
    }
  }

  async function onSolve() {
    setSolving(true)
    try {
      const res = await solveShuttles()
      setShuttles(res.report)
      setLastSolveMs(res.solved_in_ms)
      const delta = res.previous_runs - res.report.solved.runs
      say(
        delta === 0
          ? `Schedule rebuilt in ${res.solved_in_ms} ms — still ${res.report.solved.runs} runs.`
          : `Rebuilt in ${res.solved_in_ms} ms — ${delta > 0 ? delta + ' fewer' : Math.abs(delta) + ' more'} runs.`,
        'plain',
      )
    } catch (err) {
      say((err as Error).message, 'plain')
    } finally {
      setSolving(false)
    }
  }

  return (
    <div className="page host">
      <div className="topbar host-bar">
        <div className="brand">
          <BellsLogo />
          <span className="brand-name">Bells</span>
          <span className="host-tag">Host console</span>
        </div>
        <div className="host-nav">
          {wedding && (
            <span className="host-wedding">
              {wedding.couple_names} · {wedding.city}
            </span>
          )}

          <button className="btn ghost" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </div>

      {error && <p className="notice warn">{error}</p>}

      {/* the concierge comes first: most of what the couple want to do,
          they can now just say */}
      <HostChat
        onChanged={() => {
          refresh()
          getShuttles().then(setShuttles).catch(() => {})
        }}
      />

      <ImpactStrip impact={impact} minutesPerQuestion={minutes} onMinutesChange={setMinutes} />

      <OverviewPanel data={overview} />

      <div className="host-grid">
        <Inbox
          items={escalations}
          loading={loadingInbox}
          busyId={busyId}
          onApprove={onApprove}
          onDismiss={onDismiss}
        />
        <SpendPanel spend={spend} />
      </div>

      <Messages bundle={drafts} onChanged={refresh} />

      <Shuttles
        report={shuttles}
        solving={solving}
        lastSolveMs={lastSolveMs}
        onSolve={onSolve}
      />

      <Toast toast={toast} onDone={() => setToast(null)} />
    </div>
  )
}
