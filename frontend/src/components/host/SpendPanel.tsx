import type { Spend } from '../../types'

const n = (v: number) => v.toLocaleString('en-US')

function usd(v: number | null, digits = 2): string {
  if (v == null) return '—'
  return `$${v < 0.01 && v > 0 ? v.toFixed(5) : v.toFixed(digits)}`
}

export default function SpendPanel({ spend }: { spend: Spend | null }) {
  if (!spend) return <div className="panel skeleton" style={{ height: 320 }} />

  const t = spend.tokens
  const cachedPct = t.input ? Math.round((t.cached / t.input) * 100) : 0
  const unpriced = spend.cost_basis === 'unpriced'

  return (
    <section className="panel spend">
      <header className="panel-head">
        <div>
          <h2>Spend</h2>
          <p>
            {spend.turns === 0
              ? 'No turns logged yet.'
              : `${n(spend.turns)} ${spend.turns === 1 ? 'turn' : 'turns'} · ` +
                `${n(spend.guests_seen)} ${spend.guests_seen === 1 ? 'guest' : 'guests'}`}
          </p>
        </div>
        <span className="count-pill mono">{spend.model}</span>
      </header>

      <div className="panel-body">
        <div className="spend-hero">
          <div className="spend-total">{n(t.total)}</div>
          <div className="spend-total-label">tokens total</div>
        </div>

        <div
          className="bar-stack"
          role="img"
          aria-label={t.input ? `${cachedPct}% of input tokens were cached` : 'no tokens logged yet'}
        >
          {t.input > 0 && (
            <>
              <span className="bar-cached" style={{ width: `${cachedPct}%` }} />
              <span className="bar-uncached" style={{ width: `${100 - cachedPct}%` }} />
            </>
          )}
        </div>
        <div className="bar-key">
          <span>
            <i className="key cached" /> cached {n(t.cached)}
          </span>
          <span>
            <i className="key uncached" /> uncached {n(t.uncached)}
          </span>
          <span>
            <i className="key out" /> output {n(t.output)}
          </span>
        </div>

        <dl className="spend-rows">
          <div className="row">
            <dt>Cache hit rate</dt>
            <dd>{spend.cache_hit_rate == null ? '—' : `${(spend.cache_hit_rate * 100).toFixed(1)}%`}</dd>
          </div>
          <div className="row">
            <dt>Total cost</dt>
            <dd>{usd(spend.cost_usd, 4)}</dd>
          </div>
          <div className="row">
            <dt>Cost per guest</dt>
            <dd>{usd(spend.per_guest.cost_usd, 4)}</dd>
          </div>
          <div className="row">
            <dt>Tokens per guest</dt>
            <dd>{spend.per_guest.tokens == null ? '—' : n(Math.round(spend.per_guest.tokens))}</dd>
          </div>
        </dl>

        <div className="projection">
          <div className="projection-head">If this ran for {spend.projection.guests} guests</div>
          <div className="projection-figures">
            <div>
              <span className="projection-num">
                {spend.projection.tokens == null ? '—' : n(spend.projection.tokens)}
              </span>
              <span className="projection-label">tokens</span>
            </div>
            <div>
              <span className="projection-num">{usd(spend.projection.cost_usd)}</span>
              <span className="projection-label">cost</span>
            </div>
          </div>
          <p className="projection-note">
            Straight-line from the measured cost per guest — it assumes the 150th guest asks as
            much as the ones so far.
          </p>
        </div>

        {unpriced && (
          <p className="notice">
            Token counts are measured. Cost is blank because no price is set for{' '}
            <span className="code">{spend.model}</span> — add{' '}
            <span className="code">BELLS_PRICE_INPUT_PER_MTOK</span> and{' '}
            <span className="code">BELLS_PRICE_OUTPUT_PER_MTOK</span> to your{' '}
            <span className="code">.env</span> and these fill in.
          </p>
        )}
      </div>
    </section>
  )
}
