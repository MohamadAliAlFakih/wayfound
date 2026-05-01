import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { apiFetch, TOKEN_STORAGE_KEY } from '../lib/apiFetch'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_STORAGE_KEY))
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  // Rehydrate user on mount or whenever token changes (D-02 — JWT survives refresh).
  useEffect(() => {
    let cancelled = false
    async function hydrate() {
      if (!token) {
        setUser(null)
        setLoading(false)
        return
      }
      try {
        const me = await apiFetch('/me')
        if (!cancelled) setUser(me)
      } catch (err) {
        // Token invalid/expired — wipe and force re-login (T-05-04 mitigation).
        if (!cancelled) {
          localStorage.removeItem(TOKEN_STORAGE_KEY)
          setToken(null)
          setUser(null)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    setLoading(true)
    hydrate()
    return () => {
      cancelled = true
    }
  }, [token])

  const login = useCallback(async (email, password) => {
    const data = await apiFetch('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
    localStorage.setItem(TOKEN_STORAGE_KEY, data.access_token)
    setToken(data.access_token)
    return data
  }, [])

  const register = useCallback(
    async (username, email, password) => {
      await apiFetch('/auth/register', {
        method: 'POST',
        body: JSON.stringify({ username, email, password }),
      })
      // Auto-login after successful registration so the user lands in /chat.
      return await login(email, password)
    },
    [login],
  )

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
    setToken(null)
    setUser(null)
  }, [])

  const value = { token, user, login, register, logout, loading }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
