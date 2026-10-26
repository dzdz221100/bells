/**
 * The Amalfi lemon branch — the signature motif.
 *
 * Drawn after a watercolour wedding invitation: white paper, with all the
 * colour carried by the illustration rather than by a tinted background.
 * Lemons in two yellows with a lit shoulder, leaves in three greens so the
 * foliage has depth, and every shape sitting on a softer, offset copy of
 * itself — that underlay is what reads as pigment spreading into paper.
 *
 * The symbols are defined once per page and referenced everywhere else.
 */

const BRANCH_ID = 'lemon-branch'
const SPRIG_ID = 'lemon-sprig'

/** A leaf pointing right from its stem end. */
const LEAF = 'M0 0 C 14 -11, 34 -9, 44 0 C 34 9, 14 11, 0 0 Z'

function Leaf({ x, y, rotate, scale = 1, tone }: {
  x: number; y: number; rotate: number; scale?: number; tone: 1 | 2 | 3
}) {
  const fill = `var(--leaf-${tone})`
  return (
    <g transform={`translate(${x} ${y}) rotate(${rotate}) scale(${scale})`}>
      {/* the wash that bled past the edge */}
      <path d={LEAF} fill={fill} opacity="0.3" transform="translate(1.5 1.5) scale(1.07)" />
      <path d={LEAF} fill={fill} />
      <path d="M2 0 C 16 -2, 30 -2, 42 0" fill="none" stroke="var(--leaf-rib)" strokeWidth="1.1" opacity="0.5" />
    </g>
  )
}

function Lemon({ x, y, rotate = 0, scale = 1 }: {
  x: number; y: number; rotate?: number; scale?: number
}) {
  return (
    <g transform={`translate(${x} ${y}) rotate(${rotate}) scale(${scale})`}>
      <ellipse cx="0" cy="0" rx="20" ry="15" fill="var(--lemon-mid)" opacity="0.28" transform="translate(1.5 2)" />
      <ellipse cx="0" cy="0" rx="18.5" ry="13.5" fill="var(--lemon-mid)" />
      <ellipse cx="-5" cy="-4" rx="10" ry="6.5" fill="var(--lemon-light)" opacity="0.85" />
      <path d="M4 -11 C 15 -8, 19 2, 12 11 C 17 4, 15 -5, 4 -11 Z" fill="var(--lemon-shade)" opacity="0.5" />
      <path d="M17 0 C 21 -2, 23 0, 21 2 C 20 1, 19 0.5, 17 0 Z" fill="var(--lemon-shade)" opacity="0.75" />
      <ellipse cx="0" cy="0" rx="18.5" ry="13.5" fill="none" stroke="var(--lemon-shade)" strokeWidth="1" opacity="0.4" />
    </g>
  )
}

export function MotifDefs() {
  return (
    <svg width="0" height="0" aria-hidden="true" focusable="false" className="motif-defs">
      {/* a branch hanging into a corner */}
      <symbol id={BRANCH_ID} viewBox="0 0 220 180">
        <path d="M8 6 C 60 18, 104 44, 138 86 C 158 110, 176 134, 196 150"
          fill="none" stroke="var(--branch)" strokeWidth="3.4" strokeLinecap="round" opacity="0.85" />
        <path d="M96 72 C 108 86, 112 102, 110 118" fill="none" stroke="var(--branch)"
          strokeWidth="2.4" strokeLinecap="round" opacity="0.7" />
        <path d="M150 100 C 160 112, 164 124, 162 138" fill="none" stroke="var(--branch)"
          strokeWidth="2.2" strokeLinecap="round" opacity="0.7" />

        <Leaf x={30} y={16} rotate={-32} scale={1.05} tone={2} />
        <Leaf x={34} y={24} rotate={26} scale={0.9} tone={1} />
        <Leaf x={74} y={44} rotate={-48} scale={1.1} tone={3} />
        <Leaf x={86} y={58} rotate={18} scale={0.95} tone={2} />
        <Leaf x={128} y={82} rotate={-28} scale={1} tone={1} />
        <Leaf x={140} y={96} rotate={40} scale={0.85} tone={3} />
        <Leaf x={168} y={128} rotate={-18} scale={0.9} tone={2} />

        <Lemon x={110} y={128} rotate={-14} scale={1} />
        <Lemon x={163} y={147} rotate={8} scale={0.82} />
        <Lemon x={70} y={92} rotate={22} scale={0.7} />
      </symbol>

      {/* one lemon and two leaves, for card corners and repeats */}
      <symbol id={SPRIG_ID} viewBox="0 0 100 100">
        <path d="M18 16 C 38 26, 52 42, 60 60" fill="none" stroke="var(--branch)"
          strokeWidth="2.6" strokeLinecap="round" opacity="0.8" />
        <Leaf x={28} y={22} rotate={-34} scale={0.62} tone={2} />
        <Leaf x={36} y={32} rotate={22} scale={0.52} tone={1} />
        <Lemon x={62} y={68} rotate={-10} scale={0.72} />
      </symbol>
    </svg>
  )
}

/** A branch hanging into a corner. Positioned with CSS. */
export function LemonBranch({ className = '', width = 220 }: { className?: string; width?: number }) {
  return (
    <svg
      className={`lemon-branch ${className}`}
      width={width}
      height={(width * 180) / 220}
      viewBox="0 0 220 180"
      aria-hidden="true"
      focusable="false"
    >
      <use href={`#${BRANCH_ID}`} width="220" height="180" />
    </svg>
  )
}

/** A small sprig, for the corner of a card. */
export function LemonMark({ size = 46, className = '' }: { size?: number; className?: string }) {
  return (
    <svg className={`lemon-mark ${className}`} width={size} height={size} viewBox="0 0 100 100"
      aria-hidden="true" focusable="false">
      <use href={`#${SPRIG_ID}`} width="100" height="100" />
    </svg>
  )
}

/** A garland of sprigs, used as a divider. */
export function LemonGarland({ count = 30, className = '' }: { count?: number; className?: string }) {
  return (
    <div className={`lemon-garland ${className}`} aria-hidden="true">
      <svg viewBox={`0 0 ${count * 100} 100`} preserveAspectRatio="xMinYMid meet" focusable="false">
        {Array.from({ length: count }, (_, i) => (
          <use key={i} href={`#${SPRIG_ID}`} x={i * 100} y={0} width={100} height={100} />
        ))}
      </svg>
    </div>
  )
}

/** A faded field of sprigs, behind the registry grid. */
export function LemonField({ cols = 6, rows = 6 }: { cols?: number; rows?: number }) {
  return (
    <div className="lemon-field" aria-hidden="true">
      <svg viewBox={`0 0 ${cols * 100} ${rows * 100}`} preserveAspectRatio="xMidYMid slice" focusable="false">
        {Array.from({ length: rows }, (_, r) =>
          Array.from({ length: cols }, (_, c) => (
            <use key={`${r}-${c}`} href={`#${SPRIG_ID}`} x={c * 100} y={r * 100} width={100} height={100} />
          )),
        )}
      </svg>
    </div>
  )
}
