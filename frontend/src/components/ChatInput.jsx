import { useState } from 'react'

/**
 * Fixed-bottom input bar (D-05).
 *
 * Decisions enforced:
 *   D-05: textarea + Send button at the bottom.
 *   D-07: textarea + button disabled while pending — prevents double-submit
 *         (T-05-10 mitigation).
 *
 * Backend constraint (PlanTripRequest, backend/app/schemas/trips.py):
 *   query: str = Field(min_length=10, max_length=2000)
 *
 * UX:
 *   - Enter submits, Shift+Enter inserts a newline.
 *   - Send is also disabled when trimmed input < 10 chars so the user
 *     never triggers a 422 from the backend's min_length=10.
 *   - maxLength={2000} on the textarea matches the server cap (T-05-09).
 *
 * Props:
 *   onSubmit: (query: string) => void  — called with the trimmed query
 *                                        when the user submits.
 *   pending:  boolean                  — disables input while in flight.
 */
export default function ChatInput({ onSubmit, pending }) {
  const [value, setValue] = useState('')

  function handleSubmit(e) {
    e?.preventDefault()
    const trimmed = value.trim()
    if (!trimmed || pending) return
    if (trimmed.length < 10) return // backend rejects <10 chars (PlanTripRequest)
    onSubmit(trimmed)
    setValue('')
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const trimmedLen = value.trim().length
  const tooShort = trimmedLen > 0 && trimmedLen < 10

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-gray-50 px-4 py-4 flex justify-center"
    >
      <div className="w-full max-w-2xl flex flex-col gap-2">
        <div className="flex items-end gap-2 bg-white border border-gray-300 rounded-3xl shadow-sm px-4 py-2 focus-within:ring-2 focus-within:ring-emerald-500">
          <textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Describe your trip…"
            disabled={pending}
            rows={1}
            maxLength={2000}
            className="flex-1 resize-none bg-transparent border-0 focus:outline-none focus:ring-0 py-2 disabled:text-gray-400"
          />
          <button
            type="submit"
            disabled={pending || trimmedLen < 10}
            className="bg-emerald-600 text-white rounded-full w-9 h-9 flex items-center justify-center font-medium hover:bg-emerald-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            ↑
          </button>
        </div>
        {tooShort && (
          <span className="text-xs text-gray-500 px-4">
            {10 - trimmedLen} more character{10 - trimmedLen === 1 ? '' : 's'}{' '}
            needed (10 minimum)
          </span>
        )}
      </div>
    </form>
  )
}
