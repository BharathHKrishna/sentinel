import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Satellite, TrendingUp, MapPin, AlertTriangle, Flame, Trees, Trash2, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react'
import { subDays } from 'date-fns'
import MapView from '../components/MapView'
import EventCard from '../components/EventCard'
import { regionsApi, eventsApi, statsApi, adminApi } from '../api/client'
import type { Region, SentinelEvent, Stats } from '../api/client'

function StatCard({
  label, value, icon: Icon, color,
}: { label: string; value: string | number; icon: React.ElementType; color: string }) {
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
  const [allEvents, setAllEvents] = useState<SentinelEvent[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [scanningId, setScanningId] = useState<number | null>(null)
  const [scanError, setScanError] = useState<string | null>(null)
  const [scanSuccess, setScanSuccess] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [expandedRegion, setExpandedRegion] = useState<number | null>(null)

  const load = async () => {
    try {
      setLoading(true)
      setError(null)
      const [fetchedRegions, fetchedEvents, fetchedStats] = await Promise.all([
        regionsApi.list(),
        eventsApi.list({ limit: 500 }),
        statsApi.get().catch(() => null),
      ])
      setRegions(fetchedRegions)
      setAllEvents(fetchedEvents)
      if (fetchedStats) setStats(fetchedStats)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const since7d = subDays(new Date(), 7).toISOString()
  const recentEvents = allEvents.filter((e) => e.first_seen >= since7d)
  const regionMap = Object.fromEntries(regions.map((r) => [r.id, r]))
  const typeCounts = (stats?.events_by_type_7d) ?? recentEvents.reduce<Record<string, number>>((acc, e) => {
    acc[e.detected_type] = (acc[e.detected_type] ?? 0) + 1; return acc
  }, {})

  const handleScan = async (regionId: number) => {
    setScanningId(regionId)
    setScanError(null)
    setScanSuccess(null)
    try {
      await adminApi.triggerScan(regionId)
      setScanSuccess(`Scan started for "${regionMap[regionId]?.name}". Refresh in ~30s to see results.`)
      setTimeout(() => { load(); setScanSuccess(null) }, 35_000)
    } catch (err) {
      setScanError(err instanceof Error ? err.message : 'Scan failed — server may be waking up, try again in 30s.')
    } finally {
      setScanningId(null)
    }
  }

  const handleDelete = async (regionId: number) => {
    if (!confirm(`Delete "${regionMap[regionId]?.name}" and all its scan history?`)) return
    setDeletingId(regionId)
    try {
      await regionsApi.delete(regionId)
      setRegions((prev) => prev.filter((r) => r.id !== regionId))
      setAllEvents((prev) => prev.filter((e) => e.region_id !== regionId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    } finally {
      setDeletingId(null)
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
          <p className="text-gray-500 text-sm mt-1">Real-time satellite change detection</p>
        </div>
        <Link
          to="/regions/new"
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          + Add Region
        </Link>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> {error}
        </div>
      )}
      {scanError && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> {scanError}
        </div>
      )}
      {scanSuccess && (
        <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm flex items-center gap-2">
          <RefreshCw className="w-4 h-4" /> {scanSuccess}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard label="Monitored Regions" value={stats?.total_regions ?? regions.length} icon={MapPin} color="bg-blue-500" />
        <StatCard label="Changes (7 days)" value={stats?.events_7d ?? recentEvents.length} icon={TrendingUp} color="bg-orange-500" />
        <StatCard label="Fire / Burn (7d)" value={typeCounts['fire'] ?? 0} icon={Flame} color="bg-red-500" />
        <StatCard label="Deforestation (7d)" value={typeCounts['deforestation'] ?? 0} icon={Trees} color="bg-green-500" />
      </div>

      {/* Map + sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div className="lg:col-span-2 bg-white rounded-lg border border-gray-200 overflow-hidden" style={{ height: '520px' }}>
          {loading ? (
            <div className="h-full flex items-center justify-center text-gray-400">Loading map...</div>
          ) : (
            <MapView regions={regions} events={allEvents} />
          )}
        </div>

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
              <EventCard key={event.id} event={event} regionName={regionMap[event.region_id]?.name} />
            ))
          )}
          {recentEvents.length > 10 && (
            <Link to="/events" className="text-center text-sm text-blue-600 hover:underline py-2">
              View all {recentEvents.length} events →
            </Link>
          )}
        </div>
      </div>

      {/* Region list with delete + scan + history */}
      <div className="bg-white rounded-lg border border-gray-200">
        <div className="p-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">My Regions</h2>
        </div>
        {loading ? (
          <p className="p-4 text-gray-400 text-sm">Loading...</p>
        ) : regions.length === 0 ? (
          <div className="p-8 text-center text-gray-400">
            <MapPin className="w-8 h-8 mx-auto mb-2 opacity-30" />
            <p className="text-sm">No regions yet. <Link to="/regions/new" className="text-blue-600 hover:underline">Add one →</Link></p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {regions.map((region) => {
              const regionEvents = allEvents.filter((e) => e.region_id === region.id)
              const isExpanded = expandedRegion === region.id
              return (
                <div key={region.id}>
                  <div className="p-4 flex items-center justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-gray-900 truncate">{region.name}</p>
                      <p className="text-xs text-gray-500">
                        {region.detection_types.join(', ')} · every {region.cadence}h · {regionEvents.length} scans
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {regionEvents.length > 0 && (
                        <button
                          onClick={() => setExpandedRegion(isExpanded ? null : region.id)}
                          className="text-xs text-blue-600 hover:underline flex items-center gap-1"
                        >
                          History {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                        </button>
                      )}
                      <button
                        onClick={() => handleScan(region.id)}
                        disabled={scanningId === region.id}
                        className="text-xs bg-blue-50 hover:bg-blue-100 text-blue-700 px-3 py-1.5 rounded-lg disabled:opacity-50 flex items-center gap-1 transition-colors"
                      >
                        <RefreshCw className={`w-3 h-3 ${scanningId === region.id ? 'animate-spin' : ''}`} />
                        {scanningId === region.id ? 'Scanning…' : 'Scan Now'}
                      </button>
                      <button
                        onClick={() => handleDelete(region.id)}
                        disabled={deletingId === region.id}
                        className="text-xs bg-red-50 hover:bg-red-100 text-red-600 px-2 py-1.5 rounded-lg disabled:opacity-50 transition-colors"
                        title="Delete region"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                  {isExpanded && regionEvents.length > 0 && (
                    <div className="px-4 pb-4 flex flex-col gap-2 bg-gray-50">
                      {regionEvents.map((event) => (
                        <EventCard key={event.id} event={event} regionName={region.name} />
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

