import type { ChatReply } from '../types'

const n = (v: number) => v.toLocaleString('en-US')

function cost(reply: ChatReply): string {
  if (reply.cost_usd == null) return 'cost not priced'
  return `$${reply.cost_usd < 0.01 ? reply.cost_usd.toFixed(5) : reply.cost_usd.toFixed(3)}`
}

/**
 * The collapsible line under each reply: which agents and tools ran, in order,
 * and what the turn cost. This is the agent-design evidence, visible in the UI.
 */
export default function Trace({ reply }: { reply: ChatReply }) {
  const agents = reply.agents_called.length
  const tools = reply.events.length
  const t = reply.tokens

  // open by default: a guest finding this charming is the point
  return (
    <details className="trace" open>
      <summary>
        {reply.escalated && <span className="escalated-dot" title="escalated to the couple" />}
        Bells asked {agents} {agents === 1 ? 'agent' : 'agents'} · {tools}{' '}
        {tools === 1 ? 'tool' : 'tools'} · {n(t.total_tokens)} tokens · {cost(reply)}
      </summary>

      <div className="trace-body">
        <ol className="trace-steps">
          {reply.events.map((e) => (
            <li key={e.seq} className={e.status === 'refused' ? 'trace-refused' : undefined}>
              <span className="trace-seq">{e.seq}.</span>
              <span className="trace-agent">{e.agent}</span>
              <span className="trace-tool" title={e.detail}>
                {e.tool}
                {e.detail ? ` — ${e.detail}` : ''}
              </span>
              <span className="trace-ms">{Math.round(e.ms)} ms</span>
            </li>
          ))}
        </ol>

        <div className="trace-totals">
          <span>
            <b>model</b> {reply.model}
          </span>
          <span>
            <b>in</b> {n(t.input_tokens)}
          </span>
          {t.cached_tokens > 0 && (
            <span>
              <b>cached</b> {n(t.cached_tokens)}
            </span>
          )}
          <span>
            <b>out</b> {n(t.output_tokens)}
          </span>
          <span>
            <b>requests</b> {t.requests}
          </span>
          <span>
            <b>cost</b> {cost(reply)}
            {reply.cost_basis === 'unpriced' && ' (set rates in .env)'}
          </span>
          <span>
            <b>took</b> {(reply.elapsed_ms / 1000).toFixed(1)}s
          </span>
        </div>
      </div>
    </details>
  )
}
