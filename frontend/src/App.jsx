import { Routes, Route, Navigate, Link } from 'react-router-dom'
import LoginPage from './pages/LoginPage'
import ChatPage from './pages/ChatPage'
import PrivateRoute from './components/PrivateRoute'

function NotFound() {
  return (
    <div className="min-h-full flex items-center justify-center p-8 text-center">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900 mb-2">Not found</h1>
        <p className="text-gray-500 mb-4">That page doesn't exist.</p>
        <Link to="/chat" className="text-blue-600 underline">Go to chat</Link>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/chat" replace />} />
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/chat"
        element={
          <PrivateRoute>
            <ChatPage />
          </PrivateRoute>
        }
      />
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}
