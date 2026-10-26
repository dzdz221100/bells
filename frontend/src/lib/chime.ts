/**
 * The Bells chime — a little fairytale peal, synthesised in the browser.
 *
 * Not a cathedral bell: this is the glockenspiel/music-box end of the family.
 * A rising major-pentatonic sparkle, each note a soft sine with two quiet
 * harmonics above it, a gentle attack rather than a hard strike, and a quiet
 * delayed shimmer underneath so it rings off instead of stopping dead.
 * Pentatonic means no two notes can clash, however they overlap.
 *
 * Browsers block audio until the user has interacted with the page, so this is
 * only ever called from a click. The ring-on-load animation stays silent by
 * design — nobody wants a page that makes noise at them unprompted.
 */

let ctx: AudioContext | null = null

function context(): AudioContext | null {
  if (typeof window === 'undefined') return null
  const Ctor = window.AudioContext ?? (window as any).webkitAudioContext
  if (!Ctor) return null
  if (!ctx) ctx = new Ctor()
  if (ctx.state === 'suspended') void ctx.resume()
  return ctx
}

/** C major pentatonic, up high where it twinkles: C6 D6 E6 G6 A6 C7. */
const SPARKLE = [1046.5, 1174.7, 1318.5, 1568.0, 1760.0, 2093.0]

/** fundamental + two soft harmonics — bright, but not glassy. */
const PARTIALS: [ratio: number, gain: number, decay: number][] = [
  [1, 0.5, 1.9],
  [2, 0.16, 1.2],
  [3, 0.06, 0.8],
]

function note(ac: AudioContext, out: AudioNode, freq: number, at: number, level: number) {
  for (const [ratio, gain, decay] of PARTIALS) {
    const osc = ac.createOscillator()
    const amp = ac.createGain()
    osc.type = 'sine'
    osc.frequency.value = freq * ratio
    // a soft bloom rather than a hammer — this is what makes it read as "cute"
    amp.gain.setValueAtTime(0, at)
    amp.gain.linearRampToValueAtTime(gain * level, at + 0.012)
    amp.gain.exponentialRampToValueAtTime(0.0001, at + decay)
    osc.connect(amp).connect(out)
    osc.start(at)
    osc.stop(at + decay + 0.05)
  }
}

export function playChime(volume = 0.32): void {
  let ac: AudioContext | null = null
  try {
    ac = context()
  } catch {
    return // audio unavailable or blocked — the animation still plays
  }
  if (!ac) return

  // a little air taken off the top, so the sparkle never turns shrill
  const tone = ac.createBiquadFilter()
  tone.type = 'lowpass'
  tone.frequency.value = 6200
  tone.Q.value = 0.6

  const master = ac.createGain()
  master.gain.value = 1
  tone.connect(master).connect(ac.destination)

  // a quiet shimmer trailing the melody, like the sound in a bigger room
  const echo = ac.createDelay(1)
  echo.delayTime.value = 0.21
  const echoGain = ac.createGain()
  echoGain.gain.value = 0.3
  const echoFade = ac.createGain()
  echoFade.gain.value = 0.55
  master.connect(echo).connect(echoGain).connect(echoFade).connect(ac.destination)
  echoGain.connect(echo) // one soft repeat of the repeat

  const t0 = ac.currentTime + 0.02

  // the rising sparkle
  SPARKLE.forEach((f, i) => {
    note(ac, tone, f, t0 + i * 0.085, volume * (1 - i * 0.07))
  })

  // two bells answering each other at the top, a third apart
  note(ac, tone, 1568.0, t0 + 0.62, volume * 0.8)
  note(ac, tone, 1318.5, t0 + 0.75, volume * 0.7)
  note(ac, tone, 2093.0, t0 + 0.96, volume * 0.5)
}

export function chimeAvailable(): boolean {
  return typeof window !== 'undefined' &&
    Boolean(window.AudioContext ?? (window as any).webkitAudioContext)
}
