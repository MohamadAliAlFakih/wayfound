import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { apiFetch } from '../lib/apiFetch'
import MessageThread from '../components/MessageThread'
import ChatInput from '../components/ChatInput'

/**
 * Top-level chat page (D-05). Routed at /chat (wired in Plan 05-04, inside
 * <PrivateRoute>).
 *
 * State (D-08): messages live in useState here — no global store.
 *   message shape:
 *     { role: 'user' | 'assistant',
 *       content: string,
 *       tool_calls?: ToolCallOut[],   // assistant-only; from PlanTripResponse
 *       error?: boolean }              // true when the API call failed
 *
 * Submit flow (D-06, D-07, D-11, D-12):
 *   1. Append optimistic user message immediately (D-06 — before await).
 *   2. setPending(true) so MessageThread shows "Thinking…" and ChatInput
 *      disables its textarea + Send button (D-07).
 *   3. POST /api/trips/plan via apiFetch — apiFetch reads the JWT from
 *      localStorage automatically and the Vite proxy strips /api before
 *      forwarding to FastAPI on :8000 (D-12).
 *   4. On success, append the assistant message with response.answer +
 *      response.tool_calls (D-11 — single payload, no second fetch).
 *   5. On error, append a red error bubble (msg.error=true) so the user
 *      knows what went wrong without a console open.
 *   6. Always clear pending in finally — input re-enables.
 *
 * Header: Wayfound branding, the logged-in username from useAuth().user,
 * and a Logout button calling useAuth().logout(). Logout clears the token
 * synchronously; PrivateRoute (set up in 05-04) then redirects to /login
 * once token === null.
 */
export default function ChatPage() {
  const { user, logout } = useAuth()
  const [messages, setMessages] = useState([])
  const [pending, setPending] = useState(false)
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false)
  const [showMenu, setShowMenu] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const menuRef = useRef(null)

  useEffect(() => {
    if (!showMenu) return
    function handleClick(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setShowMenu(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [showMenu])

  async function handleSubmit(query) {
    // 1. Optimistic user message (D-06): append BEFORE awaiting the API.
    setMessages((prev) => [...prev, { role: 'user', content: query }])
    setPending(true)
    try {
      // 2. Hit the backend. apiFetch prepends /api → Vite proxy → :8000/trips/plan.
      const response = await apiFetch('/trips/plan', {
        method: 'POST',
        body: JSON.stringify({ query }),
      })
      // 3. Append assistant message with the full payload (D-11 — tool_calls
      //    come back inline, no second fetch needed).
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: response.answer ?? '(no answer returned)',
          tool_calls: response.tool_calls ?? [],
        },
      ])
    } catch (err) {
      // 4. Surface the error inline as a red bubble.
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Sorry, something went wrong: ${err.message}`,
          error: true,
        },
      ])
    } finally {
      // 5. Re-enable inputs (D-07).
      setPending(false)
    }
  }

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <header className="border-b border-gray-200 bg-white px-4 py-3 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <img src="/logo.svg" alt="Wayfound" className="h-8 w-8 object-contain" />
          <h1 className="text-lg font-semibold text-gray-900">Wayfound</h1>
        </div>
        <div className="flex items-center gap-3 text-sm">
          {user && (
            <span className="text-gray-600">
              Hi, <span className="font-medium">{user.username}</span>
            </span>
          )}
          <div ref={menuRef} className="relative">
            <button
              type="button"
              onClick={() => setShowMenu((v) => !v)}
              aria-label="Open menu"
              className="w-9 h-9 flex items-center justify-center rounded-full text-gray-600 hover:bg-gray-100 focus:outline-none"
            >
              <span className="text-xl leading-none">⋯</span>
            </button>
            {showMenu && (
              <div className="absolute right-0 mt-2 w-44 bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden z-40">
                <button
                  type="button"
                  onClick={() => {
                    setShowMenu(false)
                    setShowSettings(true)
                  }}
                  className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                >
                  Settings
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowMenu(false)
                    setShowLogoutConfirm(true)
                  }}
                  className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                >
                  Logout
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      <MessageThread messages={messages} pending={pending} />
      <ChatInput onSubmit={handleSubmit} pending={pending} />

      {showSettings && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
          <div className="w-full max-w-md bg-white rounded-3xl shadow-md p-8">
            <h2 className="text-xl font-semibold text-center mb-6">Settings</h2>
            <p className="text-sm text-gray-600 text-center mb-6">
              Nothing here yet. More options coming soon.
            </p>
            <button
              type="button"
              onClick={() => setShowSettings(false)}
              className="w-full bg-emerald-600 text-white py-3 rounded-full font-medium hover:bg-emerald-700"
            >
              Close
            </button>
          </div>
        </div>
      )}

      {showLogoutConfirm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
          <div className="w-full max-w-md bg-white rounded-3xl shadow-md p-8">
            <h2 className="text-xl font-semibold text-center mb-2">Log out?</h2>
            <p className="text-sm text-gray-600 text-center mb-6">
              You'll need to sign in again to use Wayfound.
            </p>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setShowLogoutConfirm(false)}
                className="flex-1 bg-gray-100 text-gray-800 py-3 rounded-full font-medium hover:bg-gray-200"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={logout}
                className="flex-1 bg-emerald-600 text-white py-3 rounded-full font-medium hover:bg-emerald-700"
              >
                Log out
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
