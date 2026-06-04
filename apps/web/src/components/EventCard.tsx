import { Link } from 'react-router-dom'
import { Flame, Trees, Waves, Building2, Sun, AlertCircle } from 'lucide-react'
import type { SentinelEvent } from '../api/client'
import { formatDistanceToNow } from 'date-fns'

interface EventCardProps {
  event: SentinelEvent
  regionName?: string
}

const TYPE_CONFIG: Record<
  string,
  { label: string; color: string; bg: string; Icon: React.ElementType }
> = {
  construction: {
    label: 'Construction',
    color: 'text-orange-700',
    bg: 'bg-orange-100',
    Icon: Building2,
  },
  deforestation: {
    label: 'Deforestation',
    color: 'text-green-700',
    bg: 'bg-green-100',
    Icon: Trees,
  },
  fire: { label: 'Fire', color: 'text-red-700', bg: 'bg-red-100', Icon: Flame },
  flood: { label: 'Flood', color: 'text-blue-700', bg: 'bg-blue-100', Icon: Waves },
  solar: { label: 'Solar Farm', color: 'text-yellow-700', bg: 'bg-yellow-100', Icon: Sun },
}

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100)
  const color =
    pct >= 75 ? 'bg-green-100 text-green-700' : pct >= 50 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {pct}% confidence
    </span>
  )
}

export default function EventCard({ event, regionName }: EventCardProps) {
  const config = TYPE_CONFIG[event.detected_type] ?? {
    label: event.detected_type,
    color: 'text-gray-700',
    bg: 'bg-gray-100',
    Icon: AlertCircle,
  }
  const { Icon, label, color, bg } = config

  const timeAgo = formatDistanceToNow(new Date(event.first_seen), { addSuffix: true })

  return (
    <Link
      to={`/events/${event.id}`}
      className="block bg-white rounded-lg border border-gray-200 p-4 hover:border-blue-300 hover:shadow-md transition-all"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className={`inline-flex p-2 rounded-lg ${bg}`}>
            <Icon className={`w-4 h-4 ${color}`} />
          </span>
          <div>
            <p className={`font-semibold text-sm ${color}`}>{label}</p>
            {regionName && <p className="text-xs text-gray-500">{regionName}</p>}
          </div>
        </div>
        <ConfidenceBadge confidence={event.confidence} />
      </div>

      {event.description && (
        <p className="mt-2 text-sm text-gray-600 line-clamp-2">{event.description}</p>
      )}

      <div className="mt-3 flex items-center justify-between text-xs text-gray-400">
        <span>
          {event.lat !== null && event.lon !== null
            ? `${event.lat.toFixed(4)}°N, ${event.lon.toFixed(4)}°E`
            : 'Location unknown'}
        </span>
        <span>{timeAgo}</span>
      </div>
    </Link>
  )
}
