import { useEffect, useState, useMemo } from 'react'
import { List, Filter, SortAsc, SortDesc } from 'lucide-react'
import EventCard from '../components/EventCard'
import { eventsApi, regionsApi } from '../api/client'
import type { SentinelEvent, Region } from '../api/client'

const TYPE_OPTIONS = [
  { value: '', label: 'All Types' },
  { value: 'construction', label: 'Construction' },
  { value: 'deforestation', label: 'Deforestation' },
  { value: 'fire', label: 'Fire' },
  { value: 'flood', label: 'Flood' },
  { value: 'solar', label: 'Solar Farm' },
]

type SortField = 'first_seen' | 'confidence'
type SortDir = 'asc' | 'desc'

export default function EventFeed() {
  const [events, setEvents] = useState<SentinelEvent[]>([])
  const [regions, setRegions] = useState<Region[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [typeFilter, setTypeFilter] = useState('')
  const [regionFilter, setRegionFilter] = useState<number | ''>('')
  const [sortField, setSortField] = useState<SortField>('first_seen')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true)
        const [fetchedEvents, fetchedRegions] = await Promise.all([
          eventsApi.list({ limit: 500 }),
          regionsApi.list(),
        ])
        setEvents(fetchedEvents)
        setRegions(fetchedRegions)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load events')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const regionMap = useMemo(
    () => Object.fromEntries(regions.map((r) => [r.id, r])),
    [regions]
  )

  const filtered = useMemo(() => {
    let result = [...events]

    if (typeFilter) result = result.filter((e) => e.detected_type === typeFilter)
    if (regionFilter !== '') result = result.filter((e) => e.region_id === regionFilter)

    result.sort((a, b) => {
      const aVal = sortField === 'first_seen' ? new Date(a.first_seen).getTime() : a.confidence
      const bVal = sortField === 'first_seen' ? new Date(b.first_seen).getTime() : b.confidence
      return sortDir === 'desc' ? bVal - aVal : aVal - bVal
    })

    return result
  }, [events, typeFilter, regionFilter, sortField, sortDir])

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))
    } else {
      setSortField(field)
      setSortDir('desc')
    }
  }

  const SortIcon = sortDir === 'desc' ? SortDesc : SortAsc

  return (
    <div className="max-w-5xl mx-auto px-4 py-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <List className="w-6 h-6 text-blue-600" />
          Event Feed
          {!loading && (
            <span className="ml-2 text-sm font-normal text-gray-500">
              ({filtered.length} of {events.length})
            </span>
          )}
        </h1>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6 flex flex-wrap gap-3 items-center">
        <Filter className="w-4 h-4 text-gray-400" />

        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {TYPE_OPTIONS.map(({ value, label }) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>

        <select
          value={regionFilter}
          onChange={(e) => setRegionFilter(e.target.value === '' ? '' : Number(e.target.value))}
          className="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">All Regions</option>
          {regions.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>

        <div className="flex gap-2 ml-auto">
          <button
            onClick={() => toggleSort('first_seen')}
            className={`flex items-center gap-1 text-sm px-3 py-1.5 rounded-md border transition-colors ${
              sortField === 'first_seen'
                ? 'border-blue-500 bg-blue-50 text-blue-700'
                : 'border-gray-300 text-gray-600 hover:bg-gray-50'
            }`}
          >
            {sortField === 'first_seen' && <SortIcon className="w-3 h-3" />}
            Date
          </button>
          <button
            onClick={() => toggleSort('confidence')}
            className={`flex items-center gap-1 text-sm px-3 py-1.5 rounded-md border transition-colors ${
              sortField === 'confidence'
                ? 'border-blue-500 bg-blue-50 text-blue-700'
                : 'border-gray-300 text-gray-600 hover:bg-gray-50'
            }`}
          >
            {sortField === 'confidence' && <SortIcon className="w-3 h-3" />}
            Confidence
          </button>
        </div>
      </div>

      {/* Event list */}
      {loading ? (
        <div className="text-center py-12 text-gray-400">Loading events...</div>
      ) : error ? (
        <div className="text-center py-12 text-red-500">{error}</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <List className="w-10 h-10 mx-auto mb-3 opacity-30" />
          <p>No events match your filters.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filtered.map((event) => (
            <EventCard
              key={event.id}
              event={event}
              regionName={regionMap[event.region_id]?.name}
            />
          ))}
        </div>
      )}
    </div>
  )
}
