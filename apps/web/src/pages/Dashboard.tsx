import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Satellite, TrendingUp, MapPin, AlertTriangle, Flame, Trees } from 'lucide-react'
import { subDays } from 'date-fns'
import MapView from '../components/MapView'
import EventCard from '../components/EventCard'
import { regionsApi, eventsApi, statsApi, adminApi } from '../api/client'
import type { Region, SentinelEvent, Stats } from '../api/client'

function StatCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string
  value: string | number
  icon: React.ElementType
  color: string
}) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 flex items-center gap-4">
      <div className={`p-3 rounded-full ${color}`}>
        <Icon className="w-5 h-5 text-white" />
      </div>
      <div>
        <p className="text-2xl font-bold text-gray-900">{value}</p>
        <p className="text-sm text-gray-500">{label}</p>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [regions, setRegions] = useState<Region[]>([])
  const [recentEvents, setRecentEvents] = useState<SentinelEvent[]>([])
  const [allEvents, setAllEvents] = useState<SentinelEvent[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [scanningAll, setScanningAll] = useState(false)

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true)
        const [fetchedRegions, fetchedEvents, fetchedStats] = await Promise.all([
          regionsApi.list(),
          eventsApi.list({ limit: 200 }),
          statsApi.get().catch(() => null),
        ])
        setRegions(fetchedRegions)
        setAllEvents(fetchedEvents)
        if (fetchedStats) setStats(fetchedStats)

        const since7d = subDays(new Date(), 7).toISOString()
        setRecentEvents(fetchedEvents.filter((e) => e.first_seen >= since7d))
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load data')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const regionMap = Object.fromEntries(regions.map((r) => [r.id, r]))

  const typeCounts = (stats?.events_by_type_7d) ?? recentEvents.reduce<Record<string, number>>((acc, e) => {
    acc[e.detected_type] = (acc[e.detected_type] ?? 0) + 1
    return acc
  }, {})

  const handleScanAll = async () => {
    setScanningAll(true)
    try {
      await adminApi.triggerScanAll()
    } finally {
      setScanningAll(false)
    }
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Satellite className="w-6 h-6 text-blue-600" />
            Sentinel Dashboard
          </h1>
          <p className="text-gray-500 text-sm mt-1">
            Real-time satellite change detection across monitored regions
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleScanAll}
            disabled={scanningAll}
            className="bg-gray-100 hover:bg-gray-200 disabled:opacity-50 text-gray-700 px-3 py-2 rounded-lg text-sm font-medium transition-colors"
            title="Trigger a scan cycle for all regions"
          >
            {scanningAll ? 'Queuing…' : 'Scan Now'}
          </button>
          <Link
            to="/regions/new"
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            + Add Region
          </Link>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" />
          {error}
        </div>
      )}

      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard
          label="Monitored Regions"
          value={stats?.total_regions ?? regions.length}
          icon={MapPin}
          color="bg-blue-500"
        />
        <StatCard
          label="Changes (last 7 days)"
          value={stats?.events_7d ?? recentEvents.length}
          icon={TrendingUp}
          color="bg-orange-500"
        />
        <StatCard
          label="Fire / Burn Scars (7d)"
          value={typeCounts['fire'] ?? 0}
          icon={Flame}
          color="bg-red-500"
        />
        <StatCard
          label="Deforestation (7d)"
          value={typeCounts['deforestation'] ?? 0}
          icon={Trees}
          color="bg-green-500"
        />
      </div>

      {/* Main layout: map + recent events */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Map */}
        <div className="lg:col-span-2 bg-white rounded-lg border border-gray-200 overflow-hidden" style={{ height: '520px' }}>
          {loading ? (
            <div className="h-full flex items-center justify-center text-gray-400">
              Loading map...
            </div>
          ) : (
            <MapView regions={regions} events={allEvents} />
          )}
        </div>

        {/* Recent events sidebar */}
        <div className="flex flex-col gap-3 overflow-y-auto" style={{ maxHeight: '520px' }}>
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide sticky top-0 bg-gray-50 py-1">
            Recent Changes
          </h2>
          {loading ? (
            <p className="text-gray-400 text-sm">Loading...</p>
          ) : recentEvents.length === 0 ? (
            <div className="text-center py-8 text-gray-400">
              <Satellite className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p className="text-sm">No changes in the last 7 days</p>
            </div>
          ) : (
            recentEvents.slice(0, 10).map((event) => (
              <EventCard
                key={event.id}
                event={event}
                regionName={regionMap[event.region_id]?.name}
              />
            ))
          )}
          {recentEvents.length > 10 && (
            <Link
              to="/events"
              className="text-center text-sm text-blue-600 hover:underline py-2"
            >
              View all {recentEvents.length} events →
            </Link>
          )}
        </div>
      </div>
    </div>
  )
}
