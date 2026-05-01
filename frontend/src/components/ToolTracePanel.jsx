import { useState } from 'react'

/**
 * Collapsible tool trace below an assistant message.
 *
 * Decisions enforced:
 *   D-09: "▶ Tools used (N)" toggle, initially collapsed.
 *   D-10: each row = "tool_name → <first 100 chars of stringified output>".
 *   D-11: tool_calls comes directly from PlanTripResponse — no second fetch.
 *
 * Backend schema (backend/app/schemas/trips.py — ToolCallOut):
 *   { tool_name: str, input: dict, output: dict|str|None,
 *     latency_ms: int|None, created_at: datetime }
 *
 * NOTE: The schema fields are `input` and `output` (NOT input_json/output_json,
 * as the CONTEXT.md describes them informally).
 *
 * Security (T-05-08): output is rendered as a React text child after
 * JSON.stringify — React escapes by default, so untrusted tool output cannot
 * inject HTML/JS. No dangerouslySetInnerHTML anywhere.
 */
export default function ToolTracePanel({ toolCalls }) {
  const [open, setOpen] = useState(false)

  if (!toolCalls || toolCalls.length === 0) return null

  return (
    <div className="mt-2 text-xs">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="text-gray-500 hover:text-gray-700 font-medium focus:outline-none"
      >
        {open ? '▼' : '▶'} Tools used ({toolCalls.length})
      </button>
      {open && (
        <ul className="mt-2 space-y-1 border-l-2 border-gray-200 pl-3">
          {toolCalls.map((tc, idx) => {
            const outStr =
              tc.output == null
                ? '(no output)'
                : typeof tc.output === 'string'
                  ? tc.output
                  : JSON.stringify(tc.output)
            const snippet =
              outStr.length > 100 ? outStr.slice(0, 100) + '…' : outStr
            return (
              <li key={idx} className="text-gray-600 break-words">
                <span className="font-mono font-semibold text-gray-800">
                  {tc.tool_name}
                </span>
                {' → '}
                <span className="font-mono text-gray-600">{snippet}</span>
                {tc.latency_ms != null && (
                  <span className="ml-2 text-gray-400">
                    ({tc.latency_ms}ms)
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
