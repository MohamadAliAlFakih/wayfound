import { useState } from 'react'

/**
 * Collapsible tool trace shown under each assistant message.
 *
 * Decisions enforced:
 *   D-09: "▶ Tools used (N)" toggle, initially collapsed.
 *   D-11: tool_calls comes directly from PlanTripResponse — no second fetch.
 *
 * Each row now renders a human-readable summary instead of raw JSON. RAG
 * results expand into a sub-list of retrieved chunks with destination, section,
 * and rank score (0 = closest match).
 *
 * Security (T-05-08): every value is rendered as a plain React text child,
 * so untrusted tool output cannot inject HTML/JS. No dangerouslySetInnerHTML.
 */
export default function ToolTracePanel({ toolCalls }) {
  const [open, setOpen] = useState(false)

  const count = toolCalls?.length ?? 0

  if (count === 0) {
    return (
      <div className="mt-2 text-xs text-gray-400 italic">
        No tools called — answer from the model directly.
      </div>
    )
  }

  return (
    <div className="mt-2 text-xs">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="text-gray-500 hover:text-gray-700 font-medium focus:outline-none"
      >
        {open ? '▼' : '▶'} Tools used ({count})
      </button>
      {open && (
        <ul className="mt-2 space-y-2 border-l-2 border-gray-200 pl-3">
          {toolCalls.map((tc, idx) => (
            <ToolRow key={idx} tc={tc} />
          ))}
        </ul>
      )}
    </div>
  )
}

function ToolRow({ tc }) {
  const icon = ICONS[tc.tool_name] ?? '🔧'
  const summary = summarize(tc)
  const ragChunks = tc.tool_name === 'rag_tool' && Array.isArray(tc.output)
    ? tc.output
    : null

  return (
    <li className="text-gray-700 break-words">
      <div>
        <span className="mr-1">{icon}</span>
        <span className="font-semibold text-gray-800">
          {humanName(tc.tool_name)}
        </span>
        {' → '}
        <span>{summary}</span>
        {tc.latency_ms != null && (
          <span className="ml-2 text-gray-400">({tc.latency_ms}ms)</span>
        )}
      </div>

      {ragChunks && ragChunks.length > 0 && (
        <ul className="mt-1 ml-6 space-y-1 text-gray-600">
          {ragChunks.map((chunk, i) => (
            <li
              key={i}
              className="text-[11px] border-l border-gray-200 pl-2"
            >
              <div>
                <span className="text-gray-400">#{chunk.score}</span>
                {typeof chunk.distance === 'number' && (
                  <span className="ml-1 text-gray-400">
                    cos={chunk.distance.toFixed(3)}
                  </span>
                )}{' '}
                <span className="font-medium text-gray-700">
                  📖 Wikivoyage · {chunk.destination}
                </span>
                {chunk.section && (
                  <span className="text-gray-500"> · {chunk.section}</span>
                )}
              </div>
              {chunk.content && (
                <div className="text-gray-500 mt-0.5 italic">
                  "{truncateText(chunk.content, 160)}"
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}

const ICONS = {
  rag_tool: '📚',
  classifier_tool: '🤖',
  weather_tool: '🌤',
  fx_tool: '💱',
}

function humanName(toolName) {
  switch (toolName) {
    case 'rag_tool':
      return 'Knowledge'
    case 'classifier_tool':
      return 'Style classifier'
    case 'weather_tool':
      return 'Weather'
    case 'fx_tool':
      return 'Currency'
    default:
      return toolName
  }
}

function summarize(tc) {
  const out = tc.output
  if (out == null) return 'no output'
  if (typeof out === 'string') return truncate(out, 80)

  switch (tc.tool_name) {
    case 'rag_tool':
      return summarizeRag(out)
    case 'classifier_tool':
      return summarizeClassifier(out)
    case 'weather_tool':
      return summarizeWeather(out, tc.input)
    case 'fx_tool':
      return summarizeFx(out, tc.input)
    default:
      return truncate(JSON.stringify(out), 80)
  }
}

function summarizeRag(out) {
  if (!Array.isArray(out)) return truncate(JSON.stringify(out), 80)
  if (out.length === 0) return 'no matches'
  const destinations = [...new Set(out.map((c) => c.destination))]
  return `${out.length} chunk${out.length === 1 ? '' : 's'} from ${destinations.join(', ')}`
}

function summarizeClassifier(out) {
  if (out?.note) return out.note
  if (out?.travel_style != null) {
    const conf = out.confidence
    const pct = typeof conf === 'number' ? ` (${Math.round(conf * 100)}% confidence)` : ''
    return `${out.travel_style}${pct}`
  }
  if (out?.error) return `error: ${out.error}`
  return truncate(JSON.stringify(out), 80)
}

function summarizeWeather(out, input) {
  if (out?.note) return out.note
  const cur = out?.current
  if (cur && cur.temp_c != null) {
    const city = cur.city ?? input?.destination ?? ''
    const desc = cur.description ?? ''
    return `${city} ${cur.temp_c}°C${desc ? `, ${desc}` : ''}`
  }
  return truncate(JSON.stringify(out), 80)
}

function summarizeFx(out, input) {
  if (out?.note) return out.note
  if (out?.rate != null) {
    const from = input?.from_currency ?? ''
    const to = input?.to_currency ?? ''
    return `1 ${from} = ${out.rate.toFixed(4)} ${to}`
  }
  return truncate(JSON.stringify(out), 80)
}

function truncate(s, n) {
  return s.length > n ? s.slice(0, n) + '…' : s
}

function truncateText(s, n) {
  if (typeof s !== 'string') return ''
  return s.length > n ? s.slice(0, n) + '…' : s
}