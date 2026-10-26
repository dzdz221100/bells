import { useState } from 'react'

/**
 * A thumbnail for a registry item.
 *
 * If the couple have put a photo URL on the item it is shown; if that URL
 * fails to load (hot-linked retailer images often do) it falls back silently
 * to a drawn one. With no photo at all, every item still gets a thumbnail —
 * line art in the wedding palette, matched to the item by keyword.
 */

type Shape =
  | 'pan' | 'plates' | 'espresso' | 'bedding' | 'board' | 'rug' | 'travel'
  | 'boat' | 'mixer' | 'glasses' | 'blanket' | 'books' | 'lantern' | 'frame' | 'gift'

function shapeFor(name: string): Shape {
  const n = name.toLowerCase()
  if (/\bpan\b|pot|casserole/.test(n)) return /casserole/.test(n) ? 'pan' : 'pan'
  if (/dinner set|plate|vietri|ceramic/.test(n)) return 'plates'
  if (/espresso|coffee/.test(n)) return 'espresso'
  if (/bedding|linen|sheet/.test(n)) return 'bedding'
  if (/board|olive-wood/.test(n)) return 'board'
  if (/rug|runner/.test(n)) return 'rug'
  if (/boat|capri|sail/.test(n)) return 'boat'
  if (/honeymoon|positano|night in/.test(n)) return 'travel'
  if (/mixer/.test(n)) return 'mixer'
  if (/glass|limoncello/.test(n)) return 'glasses'
  if (/blanket|throw/.test(n)) return 'blanket'
  if (/book|cookbook/.test(n)) return 'books'
  if (/lantern|candle|light/.test(n)) return 'lantern'
  if (/print|frame|art/.test(n)) return 'frame'
  return 'gift'
}

const C = {
  ink: 'var(--sage-deep)',
  warm: 'var(--blush-deep)',
  sage: 'var(--sage)',
  gold: 'var(--gold)',
}

function Art({ shape }: { shape: Shape }) {
  const stroke = { fill: 'none', stroke: C.ink, strokeWidth: 1.6, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
  const soft = { fill: 'none', stroke: C.sage, strokeWidth: 1.4, strokeLinecap: 'round' as const }

  switch (shape) {
    case 'pan':
      return (
        <>
          <path d="M14 30h24a2 2 0 0 1 2 2v6a10 10 0 0 1-10 10h-8a10 10 0 0 1-10-10v-6a2 2 0 0 1 2-2Z" {...stroke} />
          <path d="M40 34h8a3 3 0 0 1 0 6h-8" {...stroke} />
          <path d="M6 34h8" {...stroke} />
          <path d="M20 24c0-3 4-3 4-6M30 24c0-3 4-3 4-6" {...soft} />
        </>
      )
    case 'plates':
      return (
        <>
          <circle cx="28" cy="30" r="15" {...stroke} />
          <circle cx="28" cy="30" r="9" {...soft} />
          <circle cx="28" cy="30" r="3" fill={C.gold} stroke="none" />
          <path d="M12 46h32" {...stroke} />
          <path d="M16 50h24" {...soft} />
        </>
      )
    case 'espresso':
      return (
        <>
          <rect x="12" y="12" width="32" height="34" rx="4" {...stroke} />
          <path d="M20 20h16" {...soft} />
          <path d="M22 28h12v5a6 6 0 0 1-6 6 6 6 0 0 1-6-6v-5Z" {...stroke} />
          <path d="M24 44h8" {...soft} />
        </>
      )
    case 'bedding':
      return (
        <>
          <path d="M8 36h40v10H8z" {...stroke} />
          <path d="M8 36V26a4 4 0 0 1 4-4h32a4 4 0 0 1 4 4v10" {...stroke} />
          <rect x="14" y="26" width="12" height="7" rx="3" {...soft} />
          <rect x="30" y="26" width="12" height="7" rx="3" {...soft} />
        </>
      )
    case 'board':
      return (
        <>
          <path d="M18 14h20a4 4 0 0 1 4 4v24a4 4 0 0 1-4 4H18a4 4 0 0 1-4-4V18a4 4 0 0 1 4-4Z" {...stroke} />
          <circle cx="28" cy="20" r="2.4" {...soft} />
          <path d="M20 30h16M20 36h10" {...soft} />
        </>
      )
    case 'rug':
      return (
        <>
          <path d="M10 18h36v24H10z" {...stroke} />
          <path d="M10 14v4M18 14v4M26 14v4M34 14v4M42 14v4M46 14v4" {...soft} />
          <path d="M10 42v4M18 42v4M26 42v4M34 42v4M42 42v4M46 42v4" {...soft} />
          <path d="M18 26h20M18 34h20" {...soft} />
        </>
      )
    case 'travel':
      return (
        <>
          <rect x="12" y="20" width="32" height="26" rx="4" {...stroke} />
          <path d="M22 20v-4a3 3 0 0 1 3-3h6a3 3 0 0 1 3 3v4" {...stroke} />
          <path d="M12 32h32" {...soft} />
          <circle cx="28" cy="26" r="2" fill={C.gold} stroke="none" />
        </>
      )
    case 'boat':
      return (
        <>
          <path d="M8 40h40l-5 8H13z" {...stroke} />
          <path d="M28 36V10l12 26H28Z" {...stroke} />
          <path d="M26 36 14 24v12h12Z" {...soft} />
          <path d="M6 50c4 0 4-2 8-2s4 2 8 2 4-2 8-2 4 2 8 2 4-2 8-2" {...soft} />
        </>
      )
    case 'mixer':
      return (
        <>
          <path d="M10 46h20v4H10z" {...stroke} />
          <path d="M12 46V22a6 6 0 0 1 6-6h14" {...stroke} />
          <path d="M32 16h10a4 4 0 0 1 4 4v8H32" {...stroke} />
          <path d="M38 28v6" {...soft} />
          <path d="M32 34h12v4a8 8 0 0 1-8 8h4" {...soft} />
        </>
      )
    case 'glasses':
      return (
        <>
          <path d="M14 14h12l-2 12a4 4 0 0 1-8 0Z" {...stroke} />
          <path d="M20 30v12M15 44h10" {...stroke} />
          <path d="M30 20h12l-2 10a4 4 0 0 1-8 0Z" {...soft} />
          <path d="M36 32v10M31 44h10" {...soft} />
        </>
      )
    case 'blanket':
      return (
        <>
          <path d="M12 18c8-4 12 4 20 0s12 4 12 4v22c0 0-4-6-12-2s-12-4-20 0Z" {...stroke} />
          <path d="M14 28c8-4 12 4 20 0s10 2 10 2" {...soft} />
          <path d="M14 36c8-4 12 4 20 0s10 2 10 2" {...soft} />
        </>
      )
    case 'books':
      return (
        <>
          <path d="M12 16h12a4 4 0 0 1 4 4v24a4 4 0 0 0-4-4H12Z" {...stroke} />
          <path d="M44 16H32a4 4 0 0 0-4 4v24a4 4 0 0 1 4-4h12Z" {...stroke} />
          <path d="M28 20v24" {...soft} />
        </>
      )
    case 'lantern':
      return (
        <>
          <path d="M22 10h12" {...stroke} />
          <path d="M28 10v4" {...soft} />
          <path d="M18 18h20l-2 26H20Z" {...stroke} />
          <path d="M16 18h24M18 48h20" {...stroke} />
          <path d="M28 26c3 3 3 6 0 9-3-3-3-6 0-9Z" fill={C.gold} stroke="none" />
        </>
      )
    case 'frame':
      return (
        <>
          <rect x="10" y="14" width="36" height="30" rx="2" {...stroke} />
          <path d="M14 38l9-10 6 6 5-5 8 9" {...soft} />
          <circle cx="36" cy="22" r="2.6" fill={C.gold} stroke="none" />
          <path d="M24 48h8" {...stroke} />
        </>
      )
    default:
      return (
        <>
          <rect x="10" y="24" width="36" height="22" rx="3" {...stroke} />
          <path d="M8 18h40v6H8z" {...stroke} />
          <path d="M28 18v28" {...soft} />
          <path d="M28 18c-6 0-10-8-4-8s4 8 4 8Zm0 0c6 0 10-8 4-8s-4 8-4 8Z" {...soft} />
        </>
      )
  }
}

export default function GiftImage({ item, src }: { item: string; src: string | null }) {
  // A missing file 404s like any other broken src, so one handler covers both
  // "never fetched" and "fetched then deleted".
  const [failed, setFailed] = useState(false)

  if (src && !failed) {
    return (
      <div className="gift-img photo">
        <img src={src} alt="" loading="lazy" decoding="async" onError={() => setFailed(true)} />
      </div>
    )
  }

  return (
    <div className="gift-img drawn" aria-hidden="true">
      <svg viewBox="0 0 56 56" role="presentation">
        <Art shape={shapeFor(item)} />
      </svg>
    </div>
  )
}
