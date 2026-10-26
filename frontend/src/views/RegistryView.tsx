import { useCallback, useEffect, useState } from 'react'
import { claimRegistryItem, getRegistry, getWedding, unclaimRegistryItem } from '../api'
import GiftImage from '../components/GiftImage'
import { LemonField } from '../components/Lemons'
import Toast, { type ToastState } from '../components/host/Toast'
import type { MyRegistry, RegistryItem, Wedding } from '../types'
import { money } from '../lib/format'

let toastSeq = 0

/** Strip the scheme and path so the link reads as "johnlewis.com". */
function siteName(url: string | null): string {
  if (!url) return 'the shop'
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return 'the shop'
  }
}

function Card({
  item,
  currency,
  busy,
  onClaim,
  onUnclaim,
}: {
  item: RegistryItem
  currency: string
  busy: boolean
  onClaim: (i: RegistryItem) => void
  onUnclaim: (i: RegistryItem) => void
}) {
  const [confirming, setConfirming] = useState(false)

  const taken = !item.available && !item.claimed_by_you

  return (
    <article
      className={`gift ${item.claimed_by_you ? 'mine' : ''} ${taken ? 'taken' : ''}`}
    >
      <GiftImage item={item.item} src={item.image_url} />
      <div className="gift-top">
        <h3>{item.item}</h3>
        <span className="gift-price">{money(item.price, currency)}</span>
      </div>

      {item.url && (
        <a className="gift-link" href={item.url} target="_blank" rel="noopener noreferrer">
          View at {siteName(item.url)}
          <span aria-hidden="true"> ↗</span>
        </a>
      )}

      {taken ? (
        <div className="gift-actions">
          <span className="gift-chosen">Already chosen</span>
        </div>
      ) : item.claimed_by_you ? (
        <div className="gift-actions">
          <span className="gift-yours">
            <i aria-hidden="true" /> You’re giving this
          </span>
          <button className="btn ghost small" disabled={busy} onClick={() => onUnclaim(item)}>
            Undo
          </button>
        </div>
      ) : confirming ? (
        <div className="gift-actions">
          <button className="btn primary small" disabled={busy} onClick={() => onClaim(item)}>
            {busy ? 'Saving…' : 'Yes, it’s mine'}
          </button>
          <button className="btn ghost small" disabled={busy} onClick={() => setConfirming(false)}>
            Cancel
          </button>
          <span className="gift-note">It disappears for everyone else.</span>
        </div>
      ) : (
        <div className="gift-actions">
          <button className="btn small" disabled={busy} onClick={() => setConfirming(true)}>
            I’m buying this
          </button>
        </div>
      )}
    </article>
  )
}

type Props = { onBack: () => void }

export default function RegistryView({ onBack }: Props) {
  const [wedding, setWedding] = useState<Wedding | null>(null)
  const [data, setData] = useState<MyRegistry | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [toast, setToast] = useState<ToastState>(null)
  const [error, setError] = useState<string | null>(null)

  const say = (text: string, tone: 'ok' | 'plain' = 'ok') =>
    setToast({ id: ++toastSeq, text, tone })

  const load = useCallback(async () => {
    try {
      setData(await getRegistry())
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])

  useEffect(() => {
    getWedding().then(setWedding).catch(() => {})
    load()
  }, [load])

  async function onClaim(item: RegistryItem) {
    setBusyId(item.id)
    try {
      await claimRegistryItem(item.id)
      say(`Thank you — “${item.item}” is yours. Nobody else will see it now.`)
      await load()
    } catch (e) {
      say((e as Error).message, 'plain')
      await load()
    } finally {
      setBusyId(null)
    }
  }

  async function onUnclaim(item: RegistryItem) {
    setBusyId(item.id)
    try {
      await unclaimRegistryItem(item.id)
      say(`“${item.item}” is back on the list.`, 'plain')
      await load()
    } catch (e) {
      say((e as Error).message, 'plain')
    } finally {
      setBusyId(null)
    }
  }

  const currency = wedding?.currency ?? 'EUR'
  // available first, then the ones already spoken for, dimmed at the end
  const available = (data?.items ?? [])
    .filter((i) => !i.claimed_by_you)
    .sort((a, b) => Number(b.available) - Number(a.available))
  const yours = data?.yours ?? []

  return (
    <>
      <section className="registry-page">
        {/* the branch, large and faded, as the ground of the page */}
        <LemonField cols={7} rows={8} />

        <header className="registry-head">
          <span className="eyebrow">Gift registry</span>
          <h1>Still looking for a home</h1>
          <p>
            Tap <b>I’m buying this</b> and the gift is marked as yours, so nobody doubles
            up. Anything already spoken for is greyed out. The registry is anonymous —
            the couple see what’s left, never who chose what.
          </p>
          {data && (
            <div className="registry-stats">
              <span>
                <b>{data.available}</b> available
              </span>
              <span>
                <b>{data.taken_by_others + yours.length}</b> already chosen
              </span>
              <span>
                <b>{data.total}</b> on the list
              </span>
            </div>
          )}
        </header>

        {error && <p className="notice warn">{error}</p>}

        {yours.length > 0 && (
          <>
            <h2 className="registry-section">Your gifts</h2>
            <div className="gift-grid">
              {yours.map((i) => (
                <Card
                  key={i.id}
                  item={i}
                  currency={currency}
                  busy={busyId === i.id}
                  onClaim={onClaim}
                  onUnclaim={onUnclaim}
                />
              ))}
            </div>
          </>
        )}

        <h2 className="registry-section">
          {yours.length > 0 ? 'Still available' : ''}
        </h2>

        {data && available.length === 0 ? (
          <div className="inbox-clear">
            <span className="tick" aria-hidden="true" />
            <h3>Every gift has been chosen</h3>
            <p>Nothing left on the list — the couple will be delighted.</p>
          </div>
        ) : (
          <div className="gift-grid">
            {(data ? available : [0, 1, 2, 3, 4, 5]).map((i, n) =>
              typeof i === 'number' ? (
                <div key={n} className="skeleton" style={{ height: 150 }} />
              ) : (
                <Card
                  key={i.id}
                  item={i}
                  currency={currency}
                  busy={busyId === i.id}
                  onClaim={onClaim}
                  onUnclaim={onUnclaim}
                />
              ),
            )}
          </div>
        )}

        <footer className="registry-foot">
          <p>
            Changed your mind? Open your gift above and hit <b>Undo</b> — it goes
            straight back on the list.
          </p>
          <button className="btn ghost" onClick={onBack}>
            ← Back to the wedding page
          </button>
        </footer>
      </section>

      <Toast toast={toast} onDone={() => setToast(null)} />
    </>
  )
}
