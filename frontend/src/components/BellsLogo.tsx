import { useCallback, useEffect, useRef, useState } from 'react'
import { playChime } from '../lib/chime'

type Props = {
  /** 'sm' for the top bar, 'lg' for the sign-in card. */
  size?: 'sm' | 'lg'
  /** Ring once when the page opens. */
  autoRing?: boolean
  /** Ring again on hover (off for the small mark, so it isn't twitchy). */
  ringOnHover?: boolean
}

const RING_MS = 1700

/**
 * Two wedding bells, drawn entirely in CSS — no image, no icon font.
 *
 * They swing and chime when the page opens and whenever you click them. The
 * clappers swing against the bells rather than with them, which is what makes
 * it read as ringing instead of wobbling.
 */
export default function BellsLogo({ size = 'sm', autoRing = true, ringOnHover = false }: Props) {
  const [ringing, setRinging] = useState(false)
  const timer = useRef<number | null>(null)

  const ring = useCallback((withSound = false) => {
    if (withSound) playChime()
    if (timer.current) window.clearTimeout(timer.current)
    setRinging(false)
    document.documentElement.classList.remove('bells-ringing')
    // next frame, so re-clicking restarts the animation instead of ignoring it
    requestAnimationFrame(() => {
      setRinging(true)
      // a class on <html> is how the ring reaches the hero's gold shimmer;
      // purely presentational, and removed as soon as the peal is over
      document.documentElement.classList.add('bells-ringing')
      timer.current = window.setTimeout(() => {
        setRinging(false)
        document.documentElement.classList.remove('bells-ringing')
      }, RING_MS)
    })
  }, [])

  useEffect(() => {
    if (autoRing) ring() // silent: browsers block audio before a gesture
    return () => {
      if (timer.current) window.clearTimeout(timer.current)
      document.documentElement.classList.remove('bells-ringing')
    }
  }, [autoRing, ring])

  return (
    <button
      type="button"
      className={`bells-mark ${size} ${ringing ? 'ringing' : ''}`}
      onClick={() => ring(true)}
      onMouseEnter={ringOnHover ? () => ring(false) : undefined}
      aria-label="Ring the bells"
      title="Ring the bells"
    >
      <span className="chime" aria-hidden="true" />
      <span className="chime two" aria-hidden="true" />
      <span className="yoke" aria-hidden="true" />
      <span className="bell left" aria-hidden="true">
        <i className="clapper" />
      </span>
      <span className="bell right" aria-hidden="true">
        <i className="clapper" />
      </span>
      <span className="ribbon" aria-hidden="true" />
    </button>
  )
}
