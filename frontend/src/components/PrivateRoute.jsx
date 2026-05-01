import { Navigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function PrivateRoute({ children }) {
  const { token, loading } = useAuth()
  if (loading) {
    return <div className="p-8 text-gray-500">Loading…</div>
  }
  if (!token) {
    return <Navigate to="/login" replace />
  }
  return children
}
