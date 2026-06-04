import { MapContainer, TileLayer, Polygon, CircleMarker, Popup, useMap } from 'react-leaflet'
import { useEffect } from 'react'
import type { Region, SentinelEvent } from '../api/client'

interface MapViewProps {
  regions: Region[]
  events: SentinelEvent[]
  center?: [number, number]
  zoom?: number
  onRegionClick?: (region: Region) => void
  onEventClick?: (event: SentinelEvent) => void
}

const EVENT_COLORS: Record<string, string> = {
  construction: '#f6ad55',
  deforestation: '#48bb78',
  fire: '#fc8181',
  flood: '#63b3ed',
  solar: '#f6e05e',
}

function getEventColor(type: string): string {
  return EVENT_COLORS[type] ?? '#a0aec0'
}

/** Converts a GeoJSON Polygon coordinates array to Leaflet [lat, lon][] format */
function geojsonToLeaflet(coordinates: number[][][]): [number, number][] {
  return coordinates[0].map(([lon, lat]) => [lat, lon] as [number, number])
}

/** Auto-fit bounds when regions are loaded */
function BoundsAutoFit({ regions }: { regions: Region[] }) {
  const map = useMap()

  useEffect(() => {
    if (regions.length === 0) return
    const allPoints: [number, number][] = []
    regions.forEach((r) => {
      r.geom.coordinates[0].forEach(([lon, lat]) => allPoints.push([lat, lon]))
    })
    if (allPoints.length > 0) {
      map.fitBounds(allPoints as [number, number][], { padding: [40, 40] })
    }
  }, [regions, map])

  return null
}

export default function MapView({
  regions,
  events,
  center = [20.5937, 78.9629], // India centroid
  zoom = 5,
  onRegionClick,
  onEventClick,
}: MapViewProps) {
  return (
    <MapContainer
      center={center}
      zoom={zoom}
      style={{ height: '100%', width: '100%' }}
      scrollWheelZoom
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      <BoundsAutoFit regions={regions} />

      {/* Draw region polygons */}
      {regions.map((region) => (
        <Polygon
          key={`region-${region.id}`}
          positions={geojsonToLeaflet(region.geom.coordinates)}
          pathOptions={{
            color: '#3182ce',
            fillColor: '#3182ce',
            fillOpacity: 0.1,
            weight: 2,
          }}
          eventHandlers={{
            click: () => onRegionClick?.(region),
          }}
        >
          <Popup>
            <div className="p-1">
              <p className="font-bold text-gray-900">{region.name}</p>
              <p className="text-xs text-gray-500">
                Monitoring: {region.detection_types.join(', ') || 'all types'}
              </p>
              <p className="text-xs text-gray-500">Cadence: every {region.cadence}h</p>
            </div>
          </Popup>
        </Polygon>
      ))}

      {/* Draw event markers */}
      {events
        .filter((e) => e.lat !== null && e.lon !== null)
        .map((event) => (
          <CircleMarker
            key={`event-${event.id}`}
            center={[event.lat!, event.lon!]}
            radius={8}
            pathOptions={{
              color: getEventColor(event.detected_type),
              fillColor: getEventColor(event.detected_type),
              fillOpacity: 0.8,
              weight: 2,
            }}
            eventHandlers={{
              click: () => onEventClick?.(event),
            }}
          >
            <Popup>
              <div className="p-1">
                <p className="font-bold capitalize" style={{ color: getEventColor(event.detected_type) }}>
                  {event.detected_type}
                </p>
                <p className="text-xs text-gray-600">
                  Confidence: {(event.confidence * 100).toFixed(0)}%
                </p>
                <p className="text-xs text-gray-500">
                  {new Date(event.first_seen).toLocaleDateString()}
                </p>
                {event.description && (
                  <p className="text-xs text-gray-700 mt-1 max-w-xs">{event.description}</p>
                )}
              </div>
            </Popup>
          </CircleMarker>
        ))}
    </MapContainer>
  )
}
