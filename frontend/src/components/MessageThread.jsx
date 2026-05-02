import { useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import ToolTracePanel from './ToolTracePanel'

/**
 * Vertical message thread (D-05). Auto-scrolls to bottom when messages or the
 * pending state change. Renders all message text as plain React children so
 * React's default text-escaping handles XSS protection (T-05-07: LLM output
 * is untrusted and must not be injected as HTML).
 *
 * Props:
 *   messages: Array<{ role: 'user'|'assistant',
 *                     content: string,
 *                     tool_calls?: ToolCallOut[],
 *                     error?: boolean }>
 *   pending:  boolean — true while a /trips/plan request is in flight; renders
 *                       the "Thinking…" indicator at the bottom.
 *
 * Each assistant message with non-empty `tool_calls` renders a <ToolTracePanel>
 * directly below the bubble (D-09 — embedded child, not a sidebar).
 */
export default function MessageThread({ messages, pending }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, pending])

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4 bg-gray-50">
      {messages.length === 0 && !pending && (
        <div className="text-center text-gray-400 mt-12">
          Ask Wayfound about your next trip — climate, budget, duration, vibe.
        </div>
      )}
      {messages.map((msg, idx) => (
        <div
          key={idx}
          className={`flex ${
            msg.role === 'user' ? 'justify-end' : 'justify-start'
          }`}
        >
          <div
            className={`max-w-2xl ${
              msg.role === 'user' ? 'text-right' : 'text-left'
            }`}
          >
            <div
              className={
                msg.role === 'user'
                  ? 'inline-block bg-emerald-600 text-white rounded-2xl px-4 py-2 whitespace-pre-wrap text-left'
                  : msg.error
                    ? 'inline-block bg-red-50 border border-red-200 text-red-800 rounded-lg px-4 py-2 whitespace-pre-wrap'
                    : 'inline-block bg-gray-100 text-gray-900 rounded-2xl px-4 py-2 text-left'
              }
            >
              {msg.role === 'assistant' && !msg.error ? (
                <div className="prose prose-sm max-w-none prose-headings:mt-2 prose-headings:mb-1 prose-p:my-1 prose-ul:my-1 prose-li:my-0">
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>
              ) : (
                msg.content
              )}
            </div>
            {msg.role === 'assistant' && !msg.error && (
              <ToolTracePanel toolCalls={msg.tool_calls} />
            )}
          </div>
        </div>
      ))}
      {pending && (
        <div className="flex justify-start">
          <div className="inline-block bg-gray-100 text-gray-500 rounded-lg px-4 py-2 italic">
            Thinking<span className="inline-block animate-pulse">…</span>
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  )
}
