import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  MapContainer,
  TileLayer,
  FeatureGroup,
  Polygon,
  useMapEvents,
} from 'react-leaflet'
import { MapPin, Check, AlertTriangle, Trash2 } from 'lucide-react'
import { regionsApi } from '../api/client'

const DETECTION_TYPES = [
  { value: 'construction', label: 'New Construction' },
  { value: 'deforestation', label: 'Deforestation' },
  { value: 'fire', label: 'Fire / Burn Scars' },
  { value: 'flood', label: 'Flooding' },
  { value: 'solar', label: 'Solar Farms' },
]

const CADENCE_OPTIONS = [
  { value: 6, label: 'Every 6 hours' },
  { value: 12, label: 'Every 12 hours' },
  { value: 24, label: 'Daily' },
  { value: 72, label: 'Every 3 days' },
  { value: 168, label: 'Weekly' },
]

function MapClickHandler({
  drawing,
  onAddPoint,
}: {
  drawing: boolean
  onAddPoint: (lat: number, lng: number) => void
}) {
  useMapEvents({
    click(e) {
      if (drawing) {
        onAddPoint(e.latlng.lat, e.latlng.lng)
      }
    },
  })
  return null
}

export default function RegionEditor() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [detectionTypes, setDetectionTypes] = useState<string[]>(['construction'])
  const [cadence, setCadence] = useState(24)
  const [ownerEmail, setOwnerEmail] = useState('')
  const [polygonPoints, setPolygonPoints] = useState<[number, number][]>([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [drawing, setDrawing] = useState(false)

  const toggleType = (type: string) => {
    setDetectionTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    )
  }

  const handleAddPoint = (lat: number, lng: number) => {
    setPolygonPoints((pts) => [...pts, [lat, lng]])
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!name.trim()) { setError('Region name is required.'); return }
    if (polygonPoints.length < 3) { setError('Draw a polygon with at least 3 points on the map.'); return }
    if (detectionTypes.length === 0) { setError('Select at least one detection type.'); return }

    const ring = [...polygonPoints, polygonPoints[0]]
    const geom = {
      type: 'Polygon' as const,
      coordinates: [ring.map(([lat, lon]) => [lon, lat])],
    }

    try {
      setSubmitting(true)
      const region = await regionsApi.create({
        name,
        geom,
        detection_types: detectionTypes,
        cadence,
        owner_email: ownerEmail || null,
      })

      // If email provided, auto-subscribe
      if (ownerEmail) {
        const { alertsApi } = await import('../api/client')
        await alertsApi.subscribe({ region_id: region.id, email: ownerEmail }).catch(() => null)
      }

      navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create region')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-6">
      <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2 mb-6">
        <MapPin className="w-6 h-6 text-blue-600" />
        Add Monitoring Region
      </h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Map panel */}
        <div
          className="bg-white rounded-lg border border-gray-200 overflow-hidden flex flex-col"
          style={{ height: '500px' }}
        >
          <div className="p-2 border-b border-gray-100 flex items-center justify-between shrink-0">
            <span className="text-xs text-gray-500">
              {drawing
                ? `Click to add vertices (${polygonPoints.length} so far). Click "Done" when finished.`
                : 'Click "Draw Polygon" to start marking your region.'}
            </span>
            <div className="flex gap-2">
              {!drawing ? (
                <button
                  type="button"
                  onClick={() => { setDrawing(true); setPolygonPoints([]) }}
                  className="text-xs bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700 transition-colors"
                >
                  Draw Polygon
                </button>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => setDrawing(false)}
                    className="text-xs bg-green-600 text-white px-3 py-1 rounded hover:bg-green-700 transition-colors"
                  >
                    Done ({polygonPoints.length} pts)
                  </button>
                  <button
                    type="button"
                    onClick={() => setPolygonPoints([])}
                    className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded hover:bg-gray-200 transition-colors"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </>
              )}
            </div>
          </div>
          <div className="flex-1">
            <MapContainer
              center={[20.5937, 78.9629]}
              zoom={5}
              style={{ height: '100%', width: '100%' }}
              doubleClickZoom={false}
            >
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              <MapClickHandler drawing={drawing} onAddPoint={handleAddPoint} />
              <FeatureGroup>
                {polygonPoints.length >= 2 && (
                  <Polygon
                    positions={polygonPoints}
                    pathOptions={{ color: '#3182ce', fillColor: '#3182ce', fillOpacity: 0.2 }}
                  />
                )}
              </FeatureGroup>
            </MapContainer>
          </div>
        </div>

        {/* Form panel */}
        <form
          onSubmit={handleSubmit}
          className="bg-white rounded-lg border border-gray-200 p-6 flex flex-col gap-4"
        >
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Region Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Tumkur Solar Corridor"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              What to detect <span className="text-red-500">*</span>
            </label>
            <div className="grid grid-cols-2 gap-2">
              {DETECTION_TYPES.map(({ value, label }) => (
                <label key={value} className="flex items-center gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={detectionTypes.includes(value)}
                    onChange={() => toggleType(value)}
                    className="w-4 h-4 text-blue-600 border-gray-300 rounded"
                  />
                  <span className="text-sm text-gray-700">{label}</span>
                </label>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Scan Cadence</label>
            <select
              value={cadence}
              onChange={(e) => setCadence(Number(e.target.value))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {CADENCE_OPTIONS.map(({ value, label }) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Alert Email <span className="text-gray-400">(optional)</span>
            </label>
            <input
              type="email"
              value={ownerEmail}
              onChange={(e) => setOwnerEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <p className="text-xs text-gray-400 mt-1">
              You'll be subscribed to alerts for this region automatically.
            </p>
          </div>

          <div className="pt-2 border-t border-gray-100 text-xs text-gray-400">
            {polygonPoints.length < 3 ? (
              <span className="text-amber-600">
                Draw at least 3 points on the map to define your region.
              </span>
            ) : (
              <span className="text-green-600">
                Polygon ready: {polygonPoints.length} vertices.
              </span>
            )}
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium py-2 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            {submitting ? (
              <>
                <span className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
                Creating...
              </>
            ) : (
              <>
                <Check className="w-4 h-4" />
                Create Region
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  )
}
