import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft,
  MapPin,
  Calendar,
  TrendingUp,
  Satellite,
  Bell,
  CheckCircle,
  AlertTriangle,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react'
import { eventsApi, regionsApi, alertsApi, feedbackApi } from '../api/client'
import type { SentinelEvent, Region } from '../api/client'

const TYPE_LABELS: Record<string, string> = {
  construction: 'Construction Activity',
  deforestation: 'Deforestation',
  fire: 'Fire / Burn Scar',
  flood: 'Flooding',
  solar: 'Solar Farm Installation',
}

const TYPE_COLORS: Record<string, string> = {
  construction: 'text-orange-700 bg-orange-100 border-orange-200',
  deforestation: 'text-green-700 bg-green-100 border-green-200',
  fire: 'text-red-700 bg-red-100 border-red-200',
  flood: 'text-blue-700 bg-blue-100 border-blue-200',
  solar: 'text-yellow-700 bg-yellow-100 border-yellow-200',
}

function ConfidenceMeter({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = pct >= 75 ? 'bg-green-500' : pct >= 50 ? 'bg-yellow-400' : 'bg-red-400'
  return (
    <div>
      <div className="flex items-center justify-between text-sm mb-1">
        <span className="text-gray-600">Detection Confidence</span>
        <span className="font-semibold">{pct}%</span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2">
        <div className={`${color} h-2 rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function SubscribeForm({ regionId }: { regionId: number }) {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [msg, setMsg] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email) return
    try {
      setStatus('loading')
      await alertsApi.subscribe({ region_id: regionId, email })
      setStatus('success')
      setMsg(`You'll receive alerts at ${email}`)
    } catch (err) {
      setStatus('error')
      setMsg(err instanceof Error ? err.message : 'Subscription failed')
    }
  }

  if (status === 'success') {
    return (
      <div className="flex items-center gap-2 text-green-700 bg-green-50 border border-green-200 rounded-lg p-3 text-sm">
        <CheckCircle className="w-4 h-4 shrink-0" />
        {msg}
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="your@email.com"
        className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        required
      />
      <button
        type="submit"
        disabled={status === 'loading'}
        className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-1"
      >
        <Bell className="w-3 h-3" />
        {status === 'loading' ? 'Subscribing...' : 'Subscribe'}
      </button>
      {status === 'error' && (
        <p className="text-red-600 text-xs mt-1">{msg}</p>
      )}
    </form>
  )
}

export default function EventDetail() {
  const { id } = useParams<{ id: string }>()
  const [event, setEvent] = useState<SentinelEvent | null>(null)
  const [region, setRegion] = useState<Region | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [feedbackStatus, setFeedbackStatus] = useState<'idle' | 'loading' | 'done'>('idle')

  useEffect(() => {
    const load = async () => {
      if (!id) return
      try {
        setLoading(true)
        const fetchedEvent = await eventsApi.get(Number(id))
        setEvent(fetchedEvent)
        const fetchedRegion = await regionsApi.get(fetchedEvent.region_id)
        setRegion(fetchedRegion)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Event not found')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [id])

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-12 text-center text-gray-400">
        Loading event...
      </div>
    )
  }

  if (error || !event) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-12 text-center">
        <AlertTriangle className="w-10 h-10 text-red-400 mx-auto mb-3" />
        <p className="text-red-600">{error ?? 'Event not found'}</p>
        <Link to="/events" className="text-blue-600 hover:underline text-sm mt-2 inline-block">
          ← Back to events
        </Link>
      </div>
    )
  }

  const handleFeedback = async (isFalsePositive: boolean) => {
    if (!event) return
    setFeedbackStatus('loading')
    try {
      const updated = await feedbackApi.submit(event.id, isFalsePositive)
      setEvent(updated)
      setFeedbackStatus('done')
    } catch {
      setFeedbackStatus('idle')
    }
  }

  const typeBadgeClass = TYPE_COLORS[event.detected_type] ?? 'text-gray-700 bg-gray-100 border-gray-200'
  const typeLabel = TYPE_LABELS[event.detected_type] ?? event.detected_type

  return (
    <div className="max-w-3xl mx-auto px-4 py-6">
      {/* Back link */}
      <Link
        to="/events"
        className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Event Feed
      </Link>

      {/* Header */}
      <div className="bg-white rounded-lg border border-gray-200 p-6 mb-4">
        <div className="flex items-start justify-between mb-4">
          <div>
            <span
              className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium border ${typeBadgeClass}`}
            >
              <Satellite className="w-3.5 h-3.5" />
              {typeLabel}
            </span>
            <h1 className="text-xl font-bold text-gray-900 mt-2">
              {region?.name ?? `Region #${event.region_id}`}
            </h1>
          </div>
        </div>

        {/* Meta info */}
        <div className="grid grid-cols-2 gap-4 text-sm text-gray-600 mb-4">
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-gray-400" />
            <span>Detected {new Date(event.first_seen).toLocaleString()}</span>
          </div>
          {event.lat !== null && event.lon !== null && (
            <div className="flex items-center gap-2">
              <MapPin className="w-4 h-4 text-gray-400" />
              <span>
                {event.lat.toFixed(5)}°N, {event.lon.toFixed(5)}°E
              </span>
            </div>
          )}
        </div>

        <ConfidenceMeter value={event.confidence} />
      </div>

      {/* AI Description */}
      {event.description && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
          <p className="text-xs font-semibold text-blue-600 uppercase tracking-wide mb-1 flex items-center gap-1">
            <TrendingUp className="w-3 h-3" />
            AI Analysis
          </p>
          <p className="text-gray-700 text-sm leading-relaxed">{event.description}</p>
        </div>
      )}

      {/* Before / After tiles */}
      {(event.before_tile_url || event.after_tile_url) && (
        <div className="bg-white rounded-lg border border-gray-200 p-4 mb-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">Satellite Imagery</h2>
          <div className="grid grid-cols-2 gap-4">
            {event.before_tile_url && (
              <div>
                <p className="text-xs text-gray-500 mb-1 font-medium">Before</p>
                <a href={event.before_tile_url} target="_blank" rel="noopener noreferrer">
                  <div className="aspect-square bg-gray-100 rounded-lg border border-gray-200 flex items-center justify-center hover:border-blue-400 transition-colors overflow-hidden">
                    <img
                      src={event.before_tile_url}
                      alt="Before"
                      className="w-full h-full object-cover rounded-lg"
                      onError={(e) => {
                        ;(e.target as HTMLImageElement).style.display = 'none'
                      }}
                    />
                  </div>
                </a>
              </div>
            )}
            {event.after_tile_url && (
              <div>
                <p className="text-xs text-gray-500 mb-1 font-medium">After</p>
                <a href={event.after_tile_url} target="_blank" rel="noopener noreferrer">
                  <div className="aspect-square bg-gray-100 rounded-lg border border-gray-200 flex items-center justify-center hover:border-blue-400 transition-colors overflow-hidden">
                    <img
                      src={event.after_tile_url}
                      alt="After"
                      className="w-full h-full object-cover rounded-lg"
                      onError={(e) => {
                        ;(e.target as HTMLImageElement).style.display = 'none'
                      }}
                    />
                  </div>
                </a>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Feedback — false positive button */}
      <div className="bg-white rounded-lg border border-gray-200 p-4 mb-4">
        <h2 className="text-sm font-semibold text-gray-700 mb-1">Was this detection correct?</h2>
        <p className="text-xs text-gray-500 mb-3">
          Help improve the model — flag false positives so they're excluded from precision metrics.
        </p>
        {feedbackStatus === 'done' || event.is_false_positive !== null ? (
          <div className="flex items-center gap-2 text-sm text-gray-600">
            {event.is_false_positive === true ? (
              <><ThumbsDown className="w-4 h-4 text-red-500" /> Marked as false positive</>
            ) : event.is_false_positive === false ? (
              <><ThumbsUp className="w-4 h-4 text-green-500" /> Confirmed as real detection</>
            ) : (
              <span className="text-green-600">Feedback recorded.</span>
            )}
          </div>
        ) : (
          <div className="flex gap-3">
            <button
              onClick={() => handleFeedback(false)}
              disabled={feedbackStatus === 'loading'}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-green-300 text-green-700 hover:bg-green-50 transition-colors disabled:opacity-50"
            >
              <ThumbsUp className="w-3.5 h-3.5" />
              Yes, correct
            </button>
            <button
              onClick={() => handleFeedback(true)}
              disabled={feedbackStatus === 'loading'}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-red-300 text-red-700 hover:bg-red-50 transition-colors disabled:opacity-50"
            >
              <ThumbsDown className="w-3.5 h-3.5" />
              False positive
            </button>
          </div>
        )}
      </div>

      {/* Subscribe CTA */}
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <h2 className="text-sm font-semibold text-gray-700 mb-1 flex items-center gap-2">
          <Bell className="w-4 h-4 text-blue-500" />
          Subscribe to alerts for this region
        </h2>
        <p className="text-xs text-gray-500 mb-3">
          Receive email notifications whenever a new change is detected in{' '}
          {region?.name ?? 'this region'}.
        </p>
        <SubscribeForm regionId={event.region_id} />
      </div>
    </div>
  )
}
