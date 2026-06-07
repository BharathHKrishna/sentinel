import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  MapContainer,
  TileLayer,
  Marker,
  Rectangle,
  useMapEvents,
} from 'react-leaflet'
import { MapPin, Check, AlertTriangle } from 'lucide-react'
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

// 1024 m box half-extents in degrees (approximate)
const LAT_DELTA = 512 / 111_320
function lonDelta(lat: number) {
  return 512 / (111_320 * Math.cos((lat * Math.PI) / 180))
}

function MapClickHandler({ onPick }: { onPick: (lat: number, lon: number) => void }) {
  useMapEvents({
    click(e) {
      onPick(e.latlng.lat, e.latlng.lng)
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
  const [center, setCenter] = useState<{ lat: number; lon: number } | null>(null)
  const [latInput, setLatInput] = useState('')
  const [lonInput, setLonInput] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const toggleType = (type: string) => {
    setDetectionTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    )
  }

  const applyPoint = (lat: number, lon: number) => {
    setCenter({ lat, lon })
    setLatInput(lat.toFixed(6))
    setLonInput(lon.toFixed(6))
  }

  const handleLatLonInput = () => {
    const lat = parseFloat(latInput)
    const lon = parseFloat(lonInput)
    if (isNaN(lat) || isNaN(lon)) { setError('Enter valid lat/lon numbers.'); return }
    if (lat < -90 || lat > 90) { setError('Latitude must be between -90 and 90.'); return }
    if (lon < -180 || lon > 180) { setError('Longitude must be between -180 and 180.'); return }
    setError(null)
    applyPoint(lat, lon)
  }

  const bboxBounds = center
    ? [
        [center.lat - LAT_DELTA, center.lon - lonDelta(center.lat)],
        [center.lat + LAT_DELTA, center.lon + lonDelta(center.lat)],
      ] as [[number, number], [number, number]]
    : null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!name.trim()) { setError('Region name is required.'); return }
    if (!center) { setError('Click the map (or enter coordinates) to set a center point.'); return }
    if (detectionTypes.length === 0) { setError('Select at least one detection type.'); return }

    try {
      setSubmitting(true)
      const region = await regionsApi.create({
        name,
        lat: center.lat,
        lon: center.lon,
        detection_types: detectionTypes,
        cadence,
        owner_email: ownerEmail || null,
      })

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
          <div className="p-2 border-b border-gray-100 shrink-0">
            <p className="text-xs text-gray-500">
              Click anywhere on the map to set the center point. A 1024 m × 1024 m area will be monitored around it.
            </p>
          </div>
          <div className="flex-1">
            <MapContainer
              center={[20.5937, 78.9629]}
              zoom={5}
              style={{ height: '100%', width: '100%' }}
            >
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              <MapClickHandler onPick={applyPoint} />
              {center && (
                <>
                  <Marker position={[center.lat, center.lon]} />
                  {bboxBounds && (
                    <Rectangle
                      bounds={bboxBounds}
                      pathOptions={{ color: '#3182ce', fillColor: '#3182ce', fillOpacity: 0.15, weight: 2 }}
                    />
                  )}
                </>
              )}
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

          {/* Manual coordinate input */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Center Coordinates <span className="text-gray-400">(or click the map)</span>
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={latInput}
                onChange={(e) => setLatInput(e.target.value)}
                placeholder="Latitude"
                className="w-1/2 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <input
                type="text"
                value={lonInput}
                onChange={(e) => setLonInput(e.target.value)}
                placeholder="Longitude"
                className="w-1/2 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                type="button"
                onClick={handleLatLonInput}
                className="text-xs bg-gray-100 hover:bg-gray-200 text-gray-700 px-3 py-2 rounded-lg whitespace-nowrap"
              >
                Set
              </button>
            </div>
            {center && (
              <p className="text-xs text-green-600 mt-1">
                Monitoring 1024 m × 1024 m around {center.lat.toFixed(5)}, {center.lon.toFixed(5)}
              </p>
            )}
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

          <button
            type="submit"
            disabled={submitting}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium py-2 px-4 rounded-lg transition-colors flex items-center justify-center gap-2 mt-auto"
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
# sentinel
