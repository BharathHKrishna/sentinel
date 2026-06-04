import { Routes, Route, Link, useLocation } from 'react-router-dom'
import { Satellite, Map, List, Plus } from 'lucide-react'
import Dashboard from './pages/Dashboard'
import RegionEditor from './pages/RegionEditor'
import EventFeed from './pages/EventFeed'
import EventDetail from './pages/EventDetail'

function NavLink({ to, children }: { to: string; children: React.ReactNode }) {
  const location = useLocation()
  const active = location.pathname === to || location.pathname.startsWith(to + '/')
  return (
    <Link
      to={to}
      className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
        active
          ? 'bg-blue-100 text-blue-700'
          : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
      }`}
    >
      {children}
    </Link>
  )
}

export default function App() {
  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Top navigation */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-xl font-bold text-blue-700">
            <Satellite className="w-6 h-6" />
            Sentinel
          </Link>
          <nav className="flex items-center gap-1">
            <NavLink to="/">
              <Map className="w-4 h-4" />
              Dashboard
            </NavLink>
            <NavLink to="/events">
              <List className="w-4 h-4" />
              Events
            </NavLink>
            <NavLink to="/regions/new">
              <Plus className="w-4 h-4" />
              New Region
            </NavLink>
          </nav>
        </div>
      </header>

      {/* Page content */}
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/regions/new" element={<RegionEditor />} />
          <Route path="/events" element={<EventFeed />} />
          <Route path="/events/:id" element={<EventDetail />} />
        </Routes>
      </main>
    </div>
  )
}
