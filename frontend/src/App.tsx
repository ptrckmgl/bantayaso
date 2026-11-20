import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, ArrowDownToLine, ArrowLeft, ArrowRight, Bell, CalendarDays, Camera, Check, CheckCircle2,
  ChevronDown, ChevronRight, Clock3, Dog, Eye, Flag, LayoutDashboard,
  MapPin, Menu, Moon, PawPrint, Plus, Radio, RefreshCw, Search, Settings2, ShieldCheck,
  SlidersHorizontal, Sun, Trash2, Video, WifiOff, X, ChartNoAxesCombined, AlertTriangle, Flame,
} from 'lucide-react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, type ActivityReport, type Analytics, type Detection, type Device, type HotspotBasis, type Hotspots, type HotspotZone, type Location, type Summary } from './api'

type Page = 'overview' | 'detections' | 'cameras' | 'analytics' | 'settings'
type Theme = 'light' | 'dark'

const navigation: { id: Page; label: string; icon: typeof LayoutDashboard }[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'detections', label: 'Detections', icon: Dog },
  { id: 'cameras', label: 'CCTV Cameras', icon: Video },
  { id: 'analytics', label: 'Analytics', icon: ChartNoAxesCombined },
  { id: 'settings', label: 'Settings', icon: Settings2 },
]

const dateTime = (value: string) => new Intl.DateTimeFormat('en-PH', { timeZone: 'Asia/Manila', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(value))
const timeOnly = (value: string) => new Intl.DateTimeFormat('en-PH', { timeZone: 'Asia/Manila', hour: 'numeric', minute: '2-digit' }).format(new Date(value))
const dateOnly = (value: string) => new Intl.DateTimeFormat('en-PH', { timeZone: 'Asia/Manila', weekday: 'short', month: 'short', day: 'numeric' }).format(new Date(value))
const weekday = (value: string) => new Intl.DateTimeFormat('en-PH', { weekday: 'short', timeZone: 'Asia/Manila' }).format(new Date(`${value}T12:00:00+08:00`))

function storedNotificationIds(key: string): Set<string> {
  try {
    const stored: unknown = JSON.parse(localStorage.getItem(key) || '[]')
    return new Set(Array.isArray(stored) ? stored.filter((id): id is string => typeof id === 'string') : [])
  } catch { return new Set<string>() }
}

function detectionHeading(row: Detection): string {
  if (row.dog_count === 0) return `${row.person_count} ${row.person_count === 1 ? 'person' : 'people'} detected`
  if (row.source === 'camera' && row.track_id === null)
    return `Up to ${row.dog_count} ${row.dog_count === 1 ? 'dog' : 'dogs'} observed`
  if (row.source === 'camera' && row.snapshot_dog_count !== null)
    return `${row.snapshot_dog_count} ${row.snapshot_dog_count === 1 ? 'dog' : 'dogs'} in snapshot`
  if (row.source === 'camera' && (row.max_dogs_in_view ?? 0) > 1)
    return `Up to ${row.max_dogs_in_view} dogs together`
  if (row.source === 'camera') return `${row.dog_count} dog sighting`
  return `${row.dog_count} ${row.dog_count === 1 ? 'dog' : 'dogs'} detected`
}

// Pack size chosen in Settings; a report is a pack when at least this many dogs were seen together.
const PackSizeContext = createContext(3)
const DEFAULT_PACK_SIZE = 3
// Dogs seen together for a sustained time. Scenarios and older reports have no sustained count, so
// their peak count is used.
const groupSize = (row: Detection) => row.dogs_together ?? row.dog_count
const isPack = (row: Detection, packSize: number) => row.dog_count > 0 && groupSize(row) >= packSize

function storedPackSize(): number {
  try {
    const value = Number(localStorage.getItem('bantayaso-pack-size'))
    return Number.isInteger(value) && value >= 2 && value <= 20 ? value : DEFAULT_PACK_SIZE
  } catch { return DEFAULT_PACK_SIZE }
}

function PackBadge({ row }: { row: Detection }) {
  const packSize = useContext(PackSizeContext)
  return isPack(row, packSize) ? <span className="pack-badge" title={`${packSize} or more dogs seen together`}><Dog size={12} /> Pack of {groupSize(row)}</span> : null
}

function StatusPill({ status }: { status: string }) {
  return <span className={`status-pill status-${status}`}><span className="status-dot" />{status.charAt(0).toUpperCase() + status.slice(1)}</span>
}

function CustomDropdown<T extends string | number>({
  icon: Icon,
  value,
  options,
  onChange,
  disabled = false,
  ariaLabel,
}: {
  icon?: typeof SlidersHorizontal
  value: T
  options: { value: T; label: string }[]
  onChange: (val: T) => void
  disabled?: boolean
  ariaLabel?: string
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKey)
    }
  }, [open])

  const selectedOption = options.find(o => o.value === value)

  return (
    <div className={`custom-dropdown-wrap ${open ? 'is-open' : ''} ${disabled ? 'is-disabled' : ''}`} ref={ref}>
      <button
        type="button"
        className="custom-dropdown-trigger"
        onClick={() => !disabled && setOpen(!open)}
        aria-label={ariaLabel}
        aria-expanded={open}
        disabled={disabled}
      >
        {Icon && <Icon size={17} className="dropdown-trigger-icon" />}
        <span className="dropdown-trigger-label">{selectedOption?.label || ''}</span>
        <ChevronDown size={15} className={`dropdown-chevron ${open ? 'rotated' : ''}`} />
      </button>
      {open && (
        <div className="custom-dropdown-menu" role="listbox">
          {options.map(opt => (
            <button
              key={String(opt.value)}
              type="button"
              role="option"
              aria-selected={opt.value === value}
              className={`custom-dropdown-item ${opt.value === value ? 'selected' : ''}`}
              onClick={() => {
                onChange(opt.value)
                setOpen(false)
              }}
            >
              <span>{opt.label}</span>
              {opt.value === value && <Check size={14} className="dropdown-check" />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export function MapGraphic({ locations, devices, onSelect }: { locations: Location[]; devices: Device[]; onSelect: (id: number) => void }) {
  const spots = [
    { x: 40, y: 38 }, { x: 70, y: 58 }, { x: 28, y: 70 }, { x: 63, y: 27 },
    { x: 18, y: 32 }, { x: 82, y: 31 }, { x: 51, y: 73 }, { x: 77, y: 78 },
    { x: 34, y: 21 }, { x: 55, y: 49 }, { x: 17, y: 55 }, { x: 88, y: 51 },
  ]
  return <div className="map-graphic">
    <svg viewBox="0 0 500 290" preserveAspectRatio="none" aria-hidden="true">
      <rect width="500" height="290" fill="var(--map-ground)" />
      <path d="M0 35 C100 60 85 5 210 33 S390 75 500 25 M0 160 C120 136 144 210 245 150 S380 105 500 159 M40 290 C42 195 104 151 120 0 M290 290 C255 215 337 140 338 0 M470 290 C420 240 430 105 500 93" fill="none" stroke="var(--map-street)" strokeWidth="24" />
      <path d="M0 35 C100 60 85 5 210 33 S390 75 500 25 M0 160 C120 136 144 210 245 150 S380 105 500 159 M40 290 C42 195 104 151 120 0 M290 290 C255 215 337 140 338 0 M470 290 C420 240 430 105 500 93" fill="none" stroke="var(--map-street-line)" strokeWidth="2" strokeDasharray="8 10" opacity=".8" />
      <path d="M150 75 L225 66 L250 110 L190 135 Z M335 205 L413 192 L430 245 L363 261 Z M25 205 L95 198 L108 249 L22 266 Z" fill="var(--map-park)" opacity=".82" />
      <path d="M162 189 L206 181 L215 211 L171 219 Z M395 70 L450 75 L438 113 L391 107 Z M263 46 L301 45 L307 72 L267 75 Z" fill="var(--map-block)" />
    </svg>
    <div className="map-label map-label-one">POBLACION</div><div className="map-label map-label-two">RIVERSIDE</div>
    {locations.map((location, index) => <button key={location.id} className={`map-pin ${devices.some(d => d.location.id === location.id && d.status === 'online') ? 'is-online' : 'is-offline'}`} style={{ left: `${spots[index % spots.length].x}%`, top: `${spots[index % spots.length].y}%` }} title={location.name} onClick={() => onSelect(location.id)}><Camera size={15} /></button>)}
    <span className="map-caption">Approximate monitoring zones</span>
  </div>
}

function DetectionList({ rows, onOpen, onDelete, compact = false, emptyMessage }: { rows: Detection[]; onOpen: (row: Detection) => void; onDelete: (row: Detection) => void; compact?: boolean; emptyMessage?: string }) {
  return <div className={`detection-list ${compact ? 'compact' : ''}`}>
    {rows.length === 0 ? <div className="empty-state"><Camera size={26} /><strong>No detections to show</strong><span>{emptyMessage || 'A snapshot, count, and time will appear here after the first event. Check filters if records already exist.'}</span></div> : rows.map(row => <div className="detection-entry" key={row.id}>
      <button className="detection-row" onClick={() => onOpen(row)}>
        <div className="capture-thumb">{row.snapshot_path ? <img src={api.snapshot(row.snapshot_path)} alt={`CCTV snapshot from ${row.location.name}`} /> : <Camera size={22} />}</div>
        <div className="detection-main"><strong>{detectionHeading(row)}<PackBadge row={row} /></strong><span><MapPin size={13} /> {row.location.name} <i /> {row.device_id}{row.source === 'camera' ? ` · ${row.event_state === 'active' ? 'Active' : 'Closed'} event · ${row.person_count} ${row.person_count === 1 ? 'person' : 'people'}` : ''}</span></div>
        <div className="detection-time"><strong>{timeOnly(row.timestamp)}</strong><span>{dateOnly(row.timestamp)}</span></div>
        <StatusPill status={row.review_status} />
        <span className="row-action-space" />
      </button>
      <button className="detection-delete" title={`Delete ${row.id}`} aria-label={`Delete detection ${row.id}`} onClick={() => onDelete(row)}><Trash2 size={16} /></button>
    </div>)}
  </div>
}

const HERO_IMAGES = [
  '/hero-dogs/dog-1.jpg',
  '/hero-dogs/dog-2.jpg',
  '/hero-dogs/dog-3.jpg',
  '/hero-dogs/dog-4.jpg',
  '/hero-dogs/dog-5.jpg',
]

function EmptyOverview({ onCameras, nowLabel }: { onCameras: () => void; nowLabel: string }) {
  const [currentSlide, setCurrentSlide] = useState(0)

  useEffect(() => {
    const timer = window.setInterval(() => {
      setCurrentSlide(prev => (prev + 1) % HERO_IMAGES.length)
    }, 5000)
    return () => clearInterval(timer)
  }, [])

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" /> WELCOME TO BANTAYASO</div>
          <h1>Welcome, Operator</h1>
          <p>Your municipal monitoring workspace is active and ready to track community areas.</p>
        </div>
        <div className="heading-actions">
          <span className="date-chip"><CalendarDays size={16} />{nowLabel}</span>
        </div>
      </div>

      <section className="start-hero card start-hero-slideshow">
        <div className="hero-bg-carousel" aria-hidden="true">
          {HERO_IMAGES.map((src, idx) => (
            <div
              key={src}
              className={`hero-bg-slide ${idx === currentSlide ? 'active' : ''}`}
              style={{ backgroundImage: `url(${src})` }}
            />
          ))}
          <div className="hero-bg-overlay" />
        </div>

        <div className="start-copy">
          <h2>See what happens after<br />a camera detects a dog.</h2>
          <p>Choose <strong>Simulate a scenario</strong> in the header to create a test snapshot. Its dog count, timestamp, and monitoring zone will appear here for review.</p>
          <div className="start-actions">
            <button className="outline-button" onClick={onCameras}><Camera size={17} /> View cameras</button>
          </div>
          <small>Continuous municipal monitoring active · Detections will automatically record</small>
        </div>

        <div className="hero-slide-indicators" aria-label="Background image indicators">
          {HERO_IMAGES.map((_, idx) => (
            <button
              key={idx}
              type="button"
              className={`hero-slide-dot ${idx === currentSlide ? 'active' : ''}`}
              onClick={() => setCurrentSlide(idx)}
              title={`View slide ${idx + 1}`}
              aria-label={`View photo ${idx + 1}`}
            />
          ))}
        </div>
      </section>

      <section className="workflow-card card">
        <div className="card-header">
          <div>
            <span className="section-kicker">HOW IT WORKS</span>
            <h3>From camera to dashboard</h3>
            <p>A scenario follows the same record flow as a future camera event.</p>
          </div>
        </div>
        <div className="workflow-steps">
          <div><span className="workflow-icon"><Camera size={20} /></span><em>01</em><strong>Choose a camera</strong><p>Select its monitoring zone and dog count.</p></div>
          <ArrowRight className="workflow-arrow" size={18} />
          <div><span className="workflow-icon"><Activity size={20} /></span><em>02</em><strong>Create a snapshot</strong><p>One still image and timestamp are generated.</p></div>
          <ArrowRight className="workflow-arrow" size={18} />
          <div><span className="workflow-icon"><ShieldCheck size={20} /></span><em>03</em><strong>Save the record</strong><p>The count and image are stored together.</p></div>
          <ArrowRight className="workflow-arrow" size={18} />
          <div><span className="workflow-icon"><LayoutDashboard size={20} /></span><em>04</em><strong>Review here</strong><p>Inspect and mark the event reviewed.</p></div>
        </div>
      </section>
    </>
  )
}

function EmptyAnalytics() {
  return <><div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> MONITORING INSIGHTS</div><h1>Activity analytics</h1><p>Charts and location trends will appear after detections arrive.</p></div></div><section className="analytics-empty card"><ChartNoAxesCombined size={34} /><h2>No activity to chart yet</h2><p>Choose <strong>Simulate a scenario</strong> in the header to create the first snapshot and data point.</p></section></>
}

function CameraDetail({ device, rows, onBack, onViewHistory, onOpen, onDelete }: {
  device: Device
  rows: Detection[]
  onBack: () => void
  onViewHistory: () => void
  onOpen: (row: Detection) => void
  onDelete: (row: Detection) => void
}) {
  const latest = rows.find(row => row.snapshot_path)
  return <>
    <div className="page-heading camera-detail-heading">
      <div><div className="eyebrow"><span className="eyebrow-line" /> CCTV CAMERA</div><h1>{device.name}</h1><p><MapPin size={15} /> {device.location.name}, Barangay {device.location.barangay} · {device.id}</p></div>
      <div className="heading-actions"><button className="outline-button" onClick={onBack}><ArrowLeft size={16} /> All cameras</button><button className="outline-button" onClick={onViewHistory}>Open in Detections <ArrowRight size={16} /></button></div>
    </div>
    <section className="card camera-detail-card">
      <div className="camera-preview">{latest?.snapshot_path ? <img src={api.snapshot(latest.snapshot_path)} alt={`Latest snapshot from ${device.name}`} /> : <div className="camera-no-preview"><Camera size={32} /><span>No captures yet</span></div>}<span className="camera-preview-label"><Radio size={13} /> {latest ? 'LATEST SNAPSHOT' : 'AWAITING CAPTURE'}</span></div>
      <div className="camera-detail-info"><span className="section-kicker">REGISTERED CAMERA</span><h2>{device.name}</h2><p><MapPin size={16} /> {device.location.name}, Barangay {device.location.barangay}</p><div className="camera-detail-meta"><StatusPill status={device.status} /><span><Clock3 size={15} /> {device.last_seen ? `Last signal ${dateTime(device.last_seen)}` : 'No signal yet'}</span></div><small>{rows.length} detection{rows.length === 1 ? '' : 's'} recorded for this camera</small></div>
    </section>
    <div className="records-summary"><div><span>Camera detections</span><strong>{rows.length}</strong></div><div><span>Awaiting review</span><strong>{rows.filter(row => row.review_status === 'pending').length}</strong></div><div><span>Dog counts across events</span><strong>{rows.reduce((sum, row) => sum + row.dog_count, 0)}</strong></div></div>
    <section className="card records-card camera-detail-records"><div className="card-header"><div><span className="section-kicker">CAMERA HISTORY</span><h3>Detections at {device.location.name}</h3><p>Snapshots and reports from {device.name}</p></div></div><DetectionList rows={rows} onOpen={onOpen} onDelete={onDelete} emptyMessage={`No detections have been recorded for ${device.name} yet.`} /><div className="records-footer">Showing {rows.length} detection{rows.length === 1 ? '' : 's'} from {device.name}<span>New reports appear within a few seconds</span></div></section>
  </>
}

const hourLabel = (hour: number) => `${hour % 12 || 12} ${hour < 12 ? 'AM' : 'PM'}`
const hourRange = (hour: number | null) => hour === null ? 'No activity yet' : `${hourLabel(hour)} – ${hourLabel((hour + 1) % 24)}`
const manilaDate = (daysAgo = 0) => new Date(Date.now() + 8 * 3600e3 - daysAgo * 86400e3).toISOString().slice(0, 10)
const shortDate = (value: string) => new Intl.DateTimeFormat('en-PH', { month: 'short', day: 'numeric', timeZone: 'Asia/Manila' }).format(new Date(`${value}T12:00:00+08:00`))
const windowLabel = (hours: number) => hours === 24 ? '24 hours' : hours % 24 === 0 ? `${hours / 24} days` : `${hours} hours`
const hotspotAlertId = (zone: HotspotZone) => `hotspot-${zone.location_id}-${(zone.crossed_at || '').slice(0, 10)}`
const WINDOW_OPTIONS = [6, 12, 24, 48, 168]
type ReportRange = { start: string; end: string }
type HotspotSettings = { basis: HotspotBasis; windowHours: number; threshold: number }
// Default: a zone with 2 pack sightings in 7 days. Stored under a new key so browsers that saved the
// earlier dog-count setting start from this default.
const DEFAULT_HOTSPOT: HotspotSettings = { basis: 'packs', windowHours: 168, threshold: 2 }
const hotspotUnit = (hotspots: Hotspots | null, count = 2) => !hotspots || hotspots.basis === 'dogs' ? (count === 1 ? 'dog' : 'dogs') : `pack ${count === 1 ? 'sighting' : 'sightings'}`

function storedHotspotSettings(): HotspotSettings {
  try {
    const stored = JSON.parse(localStorage.getItem('bantayaso-hotspot-settings-v2') || '{}')
    if (stored.basis !== 'dogs' && stored.basis !== 'packs') return DEFAULT_HOTSPOT
    return {
      basis: stored.basis === 'dogs' || stored.basis === 'packs' ? stored.basis : DEFAULT_HOTSPOT.basis,
      windowHours: WINDOW_OPTIONS.includes(stored.windowHours) ? stored.windowHours : DEFAULT_HOTSPOT.windowHours,
      threshold: Number.isInteger(stored.threshold) && stored.threshold >= 1 && stored.threshold <= 1000 ? stored.threshold : DEFAULT_HOTSPOT.threshold,
    }
  } catch { return DEFAULT_HOTSPOT }
}

function HotspotCard({ hotspots, onSettings }: { hotspots: Hotspots | null; onSettings: () => void }) {
  const zones = hotspots?.zones || []
  const hot = zones.filter(zone => zone.is_hotspot)
  return <section className="card hotspot-card">
    <div className="card-header"><div><span className="section-kicker">HOTSPOT ALERTS</span><h3>{hot.length ? <><span className="hotspot-total">{hot.length}</span> {hot.length === 1 ? 'zone is' : 'zones are'} over the limit</> : 'No zone is over the limit'}</h3><p>A zone becomes a hotspot at {hotspots?.threshold ?? '–'} or more {hotspotUnit(hotspots)}{hotspots?.basis === 'packs' ? ` (${hotspots.pack_size}+ dogs together)` : ''} in the last {hotspots ? windowLabel(hotspots.window_hours) : '–'}.</p></div><button className="outline-button" onClick={onSettings}><SlidersHorizontal size={16} /> Change limit</button></div>
    <div className="hotspot-list">{zones.length === 0 ? <p className="hotspot-empty">No monitoring zones yet.</p> : zones.map(zone => <div className={`hotspot-row ${zone.is_hotspot ? 'is-hot' : ''}`} key={zone.location_id}>
      <div className="hotspot-name"><strong>{zone.name}</strong><span>{zone.barangay}</span></div>
      <div className="hotspot-meter" aria-label={`${zone.count} of ${hotspots?.threshold} ${hotspotUnit(hotspots)}`}><span style={{ width: `${Math.min(100, hotspots ? zone.count / hotspots.threshold * 100 : 0)}%` }} /></div>
      <div className="hotspot-count"><strong>{zone.count} <small>{hotspotUnit(hotspots, zone.count)}</small></strong><span>{hotspots?.basis === 'packs' ? `${zone.dogs} ${zone.dogs === 1 ? 'dog' : 'dogs'}` : `${zone.packs} ${zone.packs === 1 ? 'pack' : 'packs'}`} · {zone.reports} {zone.reports === 1 ? 'report' : 'reports'}{zone.last_seen ? ` · last ${timeOnly(zone.last_seen)}` : ''}</span></div>
      {zone.is_hotspot ? <span className="hotspot-badge"><Flame size={13} /> Hotspot</span> : <span className="hotspot-badge calm">Below limit</span>}
    </div>)}</div>
  </section>
}

function AnalyticsPage({ detections, summary, report, packSize, hotspots, range, onRange, onExportRecords, onExportReport, onSettings }: {
  detections: Detection[]; summary: Summary | null; report: ActivityReport | null; packSize: number; hotspots: Hotspots | null; range: ReportRange
  onRange: (range: ReportRange) => void; onExportRecords: () => void; onExportReport: () => void; onSettings: () => void
}) {
  const presets = [7, 30, 90]
  const today = manilaDate()
  const activePreset = presets.find(days => range.end === today && range.start === manilaDate(days - 1))
  const hourly = report?.hourly || []
  const peak = report?.peak_hour ?? null
  const zones = report?.by_location || []
  const topZone = zones[0]?.dogs ? zones[0].dogs : 0
  const tooltipStyle = { border: '1px solid var(--border)', borderRadius: 12, background: 'var(--card)', color: 'var(--text)' }
  const [hourMetric, setHourMetric] = useState<'dogs' | 'packs'>('dogs')
  const packPeak = hourly.reduce<number | null>((best, item) => item.packs > 0 && (best === null || item.packs > hourly[best].packs) ? item.hour : best, null)
  const shownPeak = hourMetric === 'dogs' ? peak : packPeak
  return <>
    <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> MONITORING INSIGHTS</div><h1>Activity analytics</h1><p>See where dogs gather, and at what time of day.</p></div><div className="heading-actions"><button className="outline-button" onClick={onExportReport} disabled={!report}><ArrowDownToLine size={17} /> Export report</button><button className="outline-button" onClick={onExportRecords}><ArrowDownToLine size={17} /> Export records</button></div></div>
    <div className="analytics-top"><div className="analytics-highlight card stat-card-green"><div className="analytics-hl-top"><span className="section-kicker">DOG COUNTS ACROSS EVENTS</span></div><strong>{detections.reduce((sum, row) => sum + row.dog_count, 0)}</strong><p>Across {summary?.total_detections || 0} recorded events</p></div><div className="analytics-highlight card stat-card-blue"><div className="analytics-hl-top"><span className="section-kicker">PACK SIGHTINGS</span></div><strong>{report?.packs ?? 0}</strong><p>Reports with {packSize} or more dogs together in the report period</p></div><div className="analytics-highlight card stat-card-amber"><div className="analytics-hl-top"><span className="section-kicker">REVIEWED EVENTS</span></div><strong>{detections.filter(row => row.review_status === 'reviewed').length}</strong><p>{summary?.pending_reviews || 0} records waiting for review</p></div></div>
    <HotspotCard hotspots={hotspots} onSettings={onSettings} />
    <section className="card range-bar" aria-label="Report period">
      <div className="range-title"><CalendarDays size={18} /><div><strong>Report period</strong><span>{report ? `${shortDate(report.start)} – ${shortDate(report.end)} · ${report.dogs} dogs in ${report.detections} reports` : 'Loading…'}</span></div></div>
      <div className="range-controls">
        <div className="range-presets" role="group" aria-label="Quick periods">{presets.map(days => <button type="button" key={days} className={activePreset === days ? 'active' : ''} aria-pressed={activePreset === days} onClick={() => onRange({ start: manilaDate(days - 1), end: today })}>Last {days} days</button>)}</div>
        <label className="date-field"><span>From</span><input type="date" value={range.start} max={range.end} onChange={event => event.target.value && onRange({ ...range, start: event.target.value })} /></label>
        <label className="date-field"><span>To</span><input type="date" value={range.end} min={range.start} max={today} onChange={event => event.target.value && onRange({ ...range, end: event.target.value })} /></label>
      </div>
    </section>
    <div className="dashboard-grid analytics-grid">
      <section className="card activity-card"><div className="card-header"><div><span className="section-kicker">DAILY TREND</span><h3>Dog counts by day</h3><p>Recorded count from all monitoring zones</p></div><span className="period-chip">{report ? `${report.daily.length} days` : '–'}</span></div><div className="chart-wrap analytics-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={report?.daily || []} margin={{ top: 12, right: 8, left: -30, bottom: 0 }}><CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 5" vertical={false} /><XAxis dataKey="date" tickFormatter={value => (report?.daily.length || 0) <= 7 ? weekday(value) : shortDate(value)} minTickGap={18} tickLine={false} axisLine={false} tick={{ fill: 'var(--muted)', fontSize: 12 }} dy={12} /><YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fill: 'var(--muted)', fontSize: 12 }} /><Tooltip contentStyle={tooltipStyle} labelFormatter={value => shortDate(String(value))} /><Area type="monotone" dataKey="dogs" name="Dogs" stroke="#10b981" strokeWidth={3} fill="#10b981" fillOpacity={.18} /></AreaChart></ResponsiveContainer></div></section>
      <section className="card location-rank"><div className="card-header"><div><span className="section-kicker">LOCATION BREAKDOWN</span><h3>Activity by zone</h3><p>Dogs recorded and each zone's busiest hour</p></div></div><div className="rank-list">{zones.map((item, index) => <div className="rank-row" key={item.location_id}><div><span className="rank-index">{String(index + 1).padStart(2, '0')}</span><strong>{item.name}</strong><span>{item.dogs} dogs</span></div><div className="rank-track"><span style={{ width: `${topZone ? (item.dogs / topZone) * 100 : 0}%` }} /></div><p className="rank-peak"><Clock3 size={13} /> {item.peak_hour === null ? 'No activity in this period' : `Most active ${hourRange(item.peak_hour)}`}{item.night_dogs > 0 ? ` · ${item.night_dogs} at night` : ''}{item.packs > 0 ? ` · ${item.packs} ${item.packs === 1 ? 'pack' : 'packs'}, largest ${item.largest_group} dogs` : ''}</p></div>)}</div></section>
    </div>
    <section className="card hourly-card"><div className="card-header"><div><span className="section-kicker">TIME OF DAY</span><h3>Activity by hour</h3><p>{hourMetric === 'dogs' ? 'Dogs recorded' : `Pack sightings (${packSize}+ dogs together)`} in each hour across the report period (Philippine time)</p></div><div className="hourly-controls"><div className="range-presets" role="group" aria-label="Show by hour"><button type="button" className={hourMetric === 'dogs' ? 'active' : ''} aria-pressed={hourMetric === 'dogs'} onClick={() => setHourMetric('dogs')}>Dogs</button><button type="button" className={hourMetric === 'packs' ? 'active' : ''} aria-pressed={hourMetric === 'packs'} onClick={() => setHourMetric('packs')}>Packs</button></div><span className="period-chip"><Clock3 size={14} /> Peak {hourRange(shownPeak)}</span></div></div><div className="chart-wrap analytics-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={hourly} margin={{ top: 12, right: 8, left: -30, bottom: 0 }}><CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 5" vertical={false} /><XAxis dataKey="hour" tickFormatter={hourLabel} interval={2} tickLine={false} axisLine={false} tick={{ fill: 'var(--muted)', fontSize: 12 }} dy={12} /><YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fill: 'var(--muted)', fontSize: 12 }} /><Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'var(--green-soft)' }} labelFormatter={value => hourRange(Number(value))} /><Bar dataKey={hourMetric} name={hourMetric === 'dogs' ? 'Dogs' : 'Packs'} radius={[6, 6, 0, 0]}>{hourly.map(item => <Cell key={item.hour} fill={item.hour === shownPeak ? '#d97706' : '#10b981'} fillOpacity={item.hour === shownPeak ? 1 : .55} />)}</Bar></BarChart></ResponsiveContainer></div></section>
  </>
}

export default function App() {
  const [page, setPage] = useState<Page>('overview')
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem('bantayaso-theme') ?? localStorage.getItem('straywatch-theme')) === 'dark' ? 'dark' : 'light')
  const [summary, setSummary] = useState<Summary | null>(null)
  const [detections, setDetections] = useState<Detection[]>([])
  const [devices, setDevices] = useState<Device[]>([])
  const [locations, setLocations] = useState<Location[]>([])
  const [analytics, setAnalytics] = useState<Analytics | null>(null)
  const [report, setReport] = useState<ActivityReport | null>(null)
  const [hotspots, setHotspots] = useState<Hotspots | null>(null)
  const [reportRange, setReportRange] = useState<ReportRange>(() => ({ start: manilaDate(6), end: manilaDate() }))
  const [hotspotSettings, setHotspotSettings] = useState<HotspotSettings>(storedHotspotSettings)
  const [packSize, setPackSize] = useState(storedPackSize)
  const packSizeRef = useRef(packSize)
  const [groupFilter, setGroupFilter] = useState<'all' | 'packs'>('all')
  const reportRangeRef = useRef(reportRange)
  const hotspotSettingsRef = useRef(hotspotSettings)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [locationFilter, setLocationFilter] = useState<number | 'all'>('all')
  const [deviceFilter, setDeviceFilter] = useState<string | 'all'>('all')
  const [selectedCameraId, setSelectedCameraId] = useState<string | null>(null)
  const [selected, setSelected] = useState<Detection | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Detection | 'all' | null>(null)
  const [addOpen, setAddOpen] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [sidebarExpanded, setSidebarExpanded] = useState(() => (localStorage.getItem('bantayaso-sidebar-expanded') ?? localStorage.getItem('straywatch-sidebar-expanded')) === 'true')
  const [scenarioOpen, setScenarioOpen] = useState(false)
  const [scenarioDevice, setScenarioDevice] = useState('')
  const [scenarioDogs, setScenarioDogs] = useState(2)
  const [toast, setToast] = useState('')
  const [working, setWorking] = useState(false)
  const [deviceForm, setDeviceForm] = useState({ id: '', name: '', location_id: 1 })
  const [useNewZone, setUseNewZone] = useState(false)
  const [zoneForm, setZoneForm] = useState({ name: '', barangay: '', description: '' })
  const [notificationOpen, setNotificationOpen] = useState(false)
  const notificationRef = useRef<HTMLDivElement>(null)
  const [readNotificationIds, setReadNotificationIds] = useState<Set<string>>(() => storedNotificationIds('bantayaso-read-notifications'))
  const [dismissedNotificationIds, setDismissedNotificationIds] = useState<Set<string>>(() => storedNotificationIds('bantayaso-dismissed-notifications'))

  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem('bantayaso-theme', theme) }, [theme])
  useEffect(() => { localStorage.setItem('bantayaso-sidebar-expanded', String(sidebarExpanded)) }, [sidebarExpanded])
  useEffect(() => { try { localStorage.setItem('bantayaso-hotspot-settings-v2', JSON.stringify(hotspotSettings)) } catch { /* settings stay for this visit */ } }, [hotspotSettings])
  useEffect(() => { try { localStorage.setItem('bantayaso-pack-size', String(packSize)) } catch { /* setting stays for this visit */ } }, [packSize])
  useEffect(() => { if (toast) { const timer = window.setTimeout(() => setToast(''), 4000); return () => clearTimeout(timer) } }, [toast])
  useEffect(() => { localStorage.setItem('bantayaso-read-notifications', JSON.stringify([...readNotificationIds])) }, [readNotificationIds])
  useEffect(() => { localStorage.setItem('bantayaso-dismissed-notifications', JSON.stringify([...dismissedNotificationIds])) }, [dismissedNotificationIds])
  useEffect(() => {
    if (!notificationOpen) return
    const closeOutside = (event: PointerEvent) => {
      if (!notificationRef.current?.contains(event.target as Node)) setNotificationOpen(false)
    }
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') setNotificationOpen(false) }
    document.addEventListener('pointerdown', closeOutside)
    document.addEventListener('keydown', closeOnEscape)
    return () => { document.removeEventListener('pointerdown', closeOutside); document.removeEventListener('keydown', closeOnEscape) }
  }, [notificationOpen])

  const refresh = useCallback(async (first = false) => {
    if (first) setLoading(true)
    try {
      const range = reportRangeRef.current, limits = hotspotSettingsRef.current, pack = packSizeRef.current
      const [s, ds, dv, loc, an, rp, hs] = await Promise.all([api.summary(), api.detections(), api.devices(), api.locations(), api.analytics(), api.report(range.start, range.end, pack), api.hotspots(limits.windowHours, limits.threshold, limits.basis, pack)])
      setSummary(s); setDetections(ds); setDevices(dv); setLocations(loc); setAnalytics(an); setError('')
      if (range === reportRangeRef.current && pack === packSizeRef.current) setReport(rp)
      if (limits === hotspotSettingsRef.current && pack === packSizeRef.current) setHotspots(hs)
      setSelected(current => current ? ds.find(item => item.id === current.id) || null : null)
    } catch (issue) { setError(issue instanceof Error ? issue.message : 'Could not connect to the local service') }
    finally { setLoading(false) }
  }, [])

  // A new report period or hotspot limit is fetched at once instead of waiting for the next refresh.
  useEffect(() => {
    reportRangeRef.current = reportRange
    packSizeRef.current = packSize
    api.report(reportRange.start, reportRange.end, packSize).then(result => { if (reportRangeRef.current === reportRange && packSizeRef.current === packSize) setReport(result) }).catch(() => { /* the full refresh reports errors */ })
  }, [reportRange, packSize])
  useEffect(() => {
    hotspotSettingsRef.current = hotspotSettings
    packSizeRef.current = packSize
    api.hotspots(hotspotSettings.windowHours, hotspotSettings.threshold, hotspotSettings.basis, packSize).then(result => { if (hotspotSettingsRef.current === hotspotSettings && packSizeRef.current === packSize) setHotspots(result) }).catch(() => { /* the full refresh reports errors */ })
  }, [hotspotSettings, packSize])

  // Check a small change counter every 5 s and reload only when the API data changed;
  // a full reload still runs every 15 s for time-based values such as today's totals.
  const revisionRef = useRef('')
  useEffect(() => {
    void refresh(true)
    const full = window.setInterval(() => { void refresh() }, 15000)
    const quick = window.setInterval(() => {
      api.revision().then(({ revision }) => {
        if (revisionRef.current && revision !== revisionRef.current) void refresh()
        revisionRef.current = revision
      }).catch(() => { /* the full reload reports connection errors */ })
    }, 5000)
    return () => { clearInterval(full); clearInterval(quick) }
  }, [refresh])

  const filtered = useMemo(() => detections.filter(row => {
    const text = `${row.id} ${row.device_id} ${row.device.name} ${row.location.name} ${row.location.barangay}`.toLowerCase()
    return text.includes(query.toLowerCase()) && (statusFilter === 'all' || row.review_status === statusFilter) && (locationFilter === 'all' || row.location.id === locationFilter) && (deviceFilter === 'all' || row.device_id === deviceFilter) && (groupFilter === 'all' || isPack(row, packSize))
  }), [detections, query, statusFilter, locationFilter, deviceFilter, groupFilter, packSize])

  const filteredDevice = deviceFilter === 'all' ? null : devices.find(device => device.id === deviceFilter)
  const selectedCamera = devices.find(device => device.id === selectedCameraId)
  const selectedCameraRows = selectedCamera ? detections.filter(row => row.device_id === selectedCamera.id) : []

  const notifications = detections.filter(row => row.review_status === 'pending' && !dismissedNotificationIds.has(row.id))
  const hotspotAlerts = (hotspots?.zones || []).filter(zone => zone.is_hotspot && !dismissedNotificationIds.has(hotspotAlertId(zone)))
  const hotspotLocationIds = new Set((hotspots?.zones || []).filter(zone => zone.is_hotspot).map(zone => zone.location_id))
  const allNoticeIds = [...hotspotAlerts.map(hotspotAlertId), ...notifications.map(row => row.id)]
  const unreadCount = allNoticeIds.filter(id => !readNotificationIds.has(id)).length
  const nowLabel = new Intl.DateTimeFormat('en-PH', { timeZone: 'Asia/Manila', weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }).format(new Date())

  async function simulate() {
    setWorking(true)
    try {
      const event = await api.simulate(scenarioDevice || devices[0]?.id, scenarioDogs)
      setScenarioOpen(false)
      setSelectedCameraId(null)
      setDeviceFilter('all')
      setLocationFilter('all')
      setPage('detections')
      await refresh()
      setToast(`Scenario saved: ${event.dog_count} ${event.dog_count === 1 ? 'dog' : 'dogs'} at ${event.location.name}`)
    }
    catch (issue) { setToast(issue instanceof Error ? issue.message : 'Could not create scenario') }
    finally { setWorking(false) }
  }

  async function updateReview(id: string, status: Detection['review_status']) {
    setWorking(true)
    try { await api.review(id, status); await refresh(); setToast(`Detection marked ${status}`) }
    catch (issue) {
      const message = issue instanceof Error ? issue.message : 'Could not update detection'
      if (message.startsWith('Local service is unavailable')) setError(message)
      setToast(message)
    }
    finally { setWorking(false) }
  }

  async function confirmDelete() {
    if (!deleteTarget) return
    setWorking(true)
    try {
      if (deleteTarget === 'all') {
        const result = await api.clearDetections()
        setSelected(null)
        setToast(`Deleted ${result.deleted} detection${result.deleted === 1 ? '' : 's'} and their snapshots`)
      } else {
        await api.deleteDetection(deleteTarget.id)
        if (selected?.id === deleteTarget.id) setSelected(null)
        setToast(`Deleted detection ${deleteTarget.id}`)
      }
      setDeleteTarget(null)
      await refresh()
    } catch (issue) { setToast(issue instanceof Error ? issue.message : 'Could not delete detection') }
    finally { setWorking(false) }
  }

  async function createDevice(event: React.FormEvent) {
    event.preventDefault()
    if (!useNewZone && !locations.some(location => location.id === deviceForm.location_id)) {
      setToast('Select an existing monitoring zone or create a new one')
      return
    }
    setWorking(true)
    try {
      const camera = await api.createDevice({
        id: deviceForm.id.trim(),
        name: deviceForm.name.trim(),
        ...(useNewZone ? { new_location: { name: zoneForm.name.trim(), barangay: zoneForm.barangay.trim(), description: zoneForm.description.trim() } } : { location_id: deviceForm.location_id }),
      })
      await refresh()
      setAddOpen(false)
      setDeviceForm({ id: '', name: '', location_id: locations[0]?.id || 1 })
      setUseNewZone(false)
      setZoneForm({ name: '', barangay: '', description: '' })
      setToast(`${camera.name} registered at ${camera.location.name}`)
    }
    catch (issue) { setToast(issue instanceof Error ? issue.message : 'Could not register camera') }
    finally { setWorking(false) }
  }

  function exportCsv() {
    const header = 'Detection ID,Timestamp,Device,Location,Peak dogs in event,Dogs in snapshot,Person count,Dogs together,Pack,Track ID,Duration seconds,Max dogs in view,Confidence,Review status,Source,Snapshot\n'
    const body = filtered.map(row => [row.id, row.timestamp, row.device_id, row.location.name, row.dog_count, row.snapshot_dog_count ?? '', row.person_count, row.dog_count ? groupSize(row) : '', isPack(row, packSize) ? 'Yes' : 'No', row.track_id ?? '', row.duration_s ?? '', row.max_dogs_in_view ?? '', row.confidence, row.review_status, row.source, row.snapshot_path ?? ''].map(value => `"${String(value).replaceAll('"', '""')}"`).join(',')).join('\n')
    const url = URL.createObjectURL(new Blob([header + body], { type: 'text/csv' }))
    const link = document.createElement('a'); link.href = url; link.download = deviceFilter === 'all' ? 'bantayaso-detections.csv' : `bantayaso-${deviceFilter}-detections.csv`; link.click(); URL.revokeObjectURL(url)
  }

  const selectPage = (next: Page) => { setPage(next); setMobileOpen(false); setNotificationOpen(false); setQuery(''); setDeviceFilter('all'); setLocationFilter('all'); setGroupFilter('all'); setSelectedCameraId(null) }

  function openCameraDetails(device: Device) {
    setPage('cameras')
    setSelectedCameraId(device.id)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function openCameraDetections(device: Device) {
    setPage('detections')
    setSelectedCameraId(null)
    setMobileOpen(false)
    setQuery('')
    setStatusFilter('all')
    setLocationFilter(device.location.id)
    setDeviceFilter(device.id)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function markNotificationsRead(ids: string[]) {
    setReadNotificationIds(current => new Set([...current, ...ids]))
  }

  function dismissNotifications(ids: string[]) {
    setDismissedNotificationIds(current => new Set([...current, ...ids]))
  }

  function openHotspot(zone: HotspotZone) {
    markNotificationsRead([hotspotAlertId(zone)])
    selectPage('analytics')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function exportReport() {
    if (!report) return
    const cell = (value: string | number) => `"${String(value).replaceAll('"', '""')}"`
    const lines: (string | number)[][] = [
      ['BantayAso activity report', `${report.start} to ${report.end}`], ['Dogs recorded', report.dogs], ['Reports', report.detections], [`Pack sightings (${report.pack_size}+ dogs together)`, report.packs], ['Peak hour', hourRange(report.peak_hour)], [],
      ['Zone', 'Barangay', 'Dogs', 'Reports', 'Pack sightings', 'Largest group', 'Dogs at night (6 PM - 6 AM)', 'Most active hour', `Hotspot now (${hotspots?.threshold ?? ''}+ ${hotspotUnit(hotspots)} in ${hotspots ? windowLabel(hotspots.window_hours) : ''})`],
      ...report.by_location.map(zone => [zone.name, zone.barangay, zone.dogs, zone.detections, zone.packs, zone.largest_group, zone.night_dogs, hourRange(zone.peak_hour), hotspotLocationIds.has(zone.location_id) ? 'Yes' : 'No']), [],
      ['Hour', 'Dogs', 'Reports', 'Pack sightings'], ...report.hourly.map(item => [hourRange(item.hour), item.dogs, item.detections, item.packs]),
    ]
    const url = URL.createObjectURL(new Blob([lines.map(line => line.map(cell).join(',')).join('\n')], { type: 'text/csv' }))
    const link = document.createElement('a'); link.href = url; link.download = `bantayaso-report-${report.start}-to-${report.end}.csv`; link.click(); URL.revokeObjectURL(url)
  }

  function openDetection(row: Detection) {
    markNotificationsRead([row.id])
    setNotificationOpen(false)
    setSelected(row)
  }

  function openNotification(row: Detection) {
    setPage('detections')
    setSelectedCameraId(null)
    setDeviceFilter(row.device_id)
    setLocationFilter(row.location.id)
    setStatusFilter('all')
    setQuery('')
    openDetection(row)
  }

  return <PackSizeContext.Provider value={packSize}><div className="app-shell">
    {mobileOpen && <button className="sidebar-scrim" aria-label="Close menu" onClick={() => setMobileOpen(false)} />}
    <aside className={`sidebar ${sidebarExpanded ? 'expanded' : ''} ${mobileOpen ? 'mobile-open' : ''}`} onClick={event => {
      if (window.matchMedia('(max-width: 1024px)').matches) return
      // Nav buttons (and the gaps between them) navigate only; every other part of the sidebar toggles it.
      if ((event.target as Element).closest('.nav-list')) return
      setSidebarExpanded(value => !value)
    }}>
      <div className="brand-header-row">
        <button className="brand" type="button" title={sidebarExpanded ? 'Collapse sidebar' : 'Expand sidebar'} aria-label={sidebarExpanded ? 'Collapse sidebar' : 'Expand sidebar'} aria-expanded={sidebarExpanded}>
          <span className="brand-icon"><img src="/bantayaso-logo.png" alt="BantayAso" className="brand-logo-img" /></span>
          <span className="brand-name"><strong>BantayAso<span>.</span></strong></span>
        </button>
        {mobileOpen && (
          <button className="sidebar-close-btn" type="button" aria-label="Close menu" onClick={() => setMobileOpen(false)}>
            <X size={18} />
          </button>
        )}
      </div>
      <div className="nav-section-label">WORKSPACE</div>
      <nav className="nav-list" aria-label="Main navigation">{navigation.slice(0, 4).map(item => <button key={item.id} title={item.label} aria-label={item.label} aria-current={page === item.id ? 'page' : undefined} className={`nav-item ${page === item.id ? 'active' : ''}`} onClick={() => { selectPage(item.id); setMobileOpen(false) }}><item.icon size={19} strokeWidth={2} /><span>{item.label}</span>{item.id === 'detections' && unreadCount > 0 && <em>{unreadCount}</em>}</button>)}</nav>
      <div className="nav-section-label nav-section-second">SYSTEM</div>
      <nav className="nav-list"><button title="Settings" aria-label="Settings" aria-current={page === 'settings' ? 'page' : undefined} className={`nav-item ${page === 'settings' ? 'active' : ''}`} onClick={() => { selectPage('settings'); setMobileOpen(false) }}><Settings2 size={19} /><span>Settings</span></button></nav>
    </aside>

    <main className="main-panel">
      <header className="topbar"><div className="topbar-left"><button className="icon-button mobile-menu" aria-label={mobileOpen ? 'Close menu' : 'Toggle navigation menu'} title={mobileOpen ? 'Close menu' : 'Toggle navigation menu'} onClick={() => { if (window.matchMedia('(max-width: 1024px)').matches) { setMobileOpen(open => !open) } else { setSidebarExpanded(exp => !exp) } }}>{mobileOpen ? <X size={21} /> : <Menu size={21} />}</button><span className="breadcrumb-root">Workspace</span><ChevronRight size={16} /><strong>{navigation.find(item => item.id === page)?.label}</strong></div><div className="topbar-actions"><div className={'live-indicator ' + (error ? 'offline' : '')}><span /> {error ? 'Service offline' : 'Service connected'}</div><button className="primary-button scenario-trigger" aria-label="Simulate a scenario" disabled={working || devices.length === 0 || !!error} onClick={() => { setScenarioDevice(devices[0]?.id || ''); setScenarioOpen(true) }}><Plus size={16} /><span>Simulate a scenario</span></button><button className="icon-button" title="Toggle dark mode" aria-label="Toggle dark mode" onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>{theme === 'light' ? <Moon size={19} /> : <Sun size={19} />}</button><div className="notification-wrap" ref={notificationRef}>
        <button type="button" className="icon-button notification-button" title="Notifications" aria-label={`Notifications, ${unreadCount} unread`} aria-expanded={notificationOpen} aria-controls="notification-panel" onClick={() => setNotificationOpen(open => !open)}>
          <Bell size={19} />{unreadCount > 0 && <span className="notification-count">{unreadCount > 99 ? '99+' : unreadCount}</span>}
        </button>
        {notificationOpen && <section id="notification-panel" className="notification-panel" aria-labelledby="notification-title">
          <div className="notification-header"><div><h2 id="notification-title">Notifications</h2><p>{unreadCount} unread | {allNoticeIds.length} notices</p></div><button type="button" onClick={() => markNotificationsRead(allNoticeIds)} disabled={unreadCount === 0}>Mark all read</button></div>
          <div className="notification-list">{allNoticeIds.length === 0
            ? <div className="notification-empty"><Bell size={23} /><strong>You're all caught up</strong><span>New detections and hotspot alerts will appear here.</span></div>
            : <>{hotspotAlerts.map(zone => { const id = hotspotAlertId(zone); const unread = !readNotificationIds.has(id); return <div key={id} className={`notification-item hotspot-notice ${unread ? 'unread' : ''}`}>
              <button type="button" className="notification-open" onClick={() => openHotspot(zone)} aria-label={`Open hotspot alert for ${zone.name}`}>
                <span className="notification-thumb hotspot-thumb"><Flame size={20} /></span>
                <span className="notification-copy"><strong>Hotspot: {zone.name}</strong><small>{zone.count} {hotspotUnit(hotspots, zone.count)} in the last {hotspots ? windowLabel(hotspots.window_hours) : ''} | limit {hotspots?.threshold}</small>{zone.crossed_at && <time dateTime={zone.crossed_at}>Reached {dateTime(zone.crossed_at)}</time>}</span>
                {unread && <span className="notification-new">New</span>}
              </button>
              <button type="button" className="notification-dismiss" title="Dismiss notification" aria-label={`Dismiss hotspot alert for ${zone.name}`} onClick={() => dismissNotifications([id])}><X size={16} /></button>
            </div> })}{notifications.slice(0, 6).map(row => <div key={row.id} className={`notification-item ${!readNotificationIds.has(row.id) ? 'unread' : ''}`}>
              <button type="button" className="notification-open" onClick={() => openNotification(row)} aria-label={`Open ${detectionHeading(row)} at ${row.location.name}`}>
                <span className="notification-thumb">{row.snapshot_path ? <img src={api.snapshot(row.snapshot_path)} alt="" /> : <Camera size={20} />}</span>
                <span className="notification-copy"><strong>{isPack(row, packSize) ? `Pack of ${groupSize(row)} dogs` : detectionHeading(row)}</strong><small>{row.device.name} | {row.location.name}</small><time dateTime={row.timestamp}>{dateTime(row.timestamp)}</time></span>
                {!readNotificationIds.has(row.id) && <span className="notification-new">New</span>}
              </button>
              <button type="button" className="notification-dismiss" title="Dismiss notification" aria-label={`Dismiss notification for ${detectionHeading(row)} at ${row.location.name}`} onClick={() => dismissNotifications([row.id])}><X size={16} /></button>
            </div>)}</>}
          </div>
          <div className="notification-footer"><span>{notifications.length > 6 ? `Showing latest 6 of ${notifications.length}` : `${notifications.length} shown`}</span><div><button type="button" onClick={() => dismissNotifications(allNoticeIds)} disabled={allNoticeIds.length === 0}>Clear all</button><button type="button" onClick={() => { selectPage('detections'); setStatusFilter('pending') }}>View all</button></div></div>
          <p className="notification-note">Clearing hides notices in this browser; detection records remain available for review.</p>
        </section>}
      </div></div></header>

      <div className="content">
        {error && <div className="error-banner"><WifiOff size={18} /><span>{error}</span><button onClick={() => void refresh()}>Retry</button></div>}
        {loading && !summary ? <div className="loading-state"><RefreshCw className="spin" size={28} /><strong>Loading monitoring data…</strong></div> : <>
          {page === 'overview' && detections.length === 0 && <EmptyOverview onCameras={() => selectPage('cameras')} nowLabel={nowLabel} />}
          {page === 'overview' && detections.length > 0 && <>
            <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> DETECTION OVERVIEW</div><h1>Good day, Operator</h1><p>Here's what's happening across your monitored areas today.</p></div><div className="heading-actions"><span className="date-chip"><CalendarDays size={16} />{nowLabel}</span></div></div>
            <div className="hero-card"><div className="hero-content"><div className="hero-badge"><span className="hero-badge-dot" /> DETECTION RECORDS</div><h2>Keeping our streets<br />safer, one event<br />at a time.</h2><p>Review incoming detection records, snapshots, and locations in one place.</p><button onClick={() => selectPage('detections')}>Explore detections <ArrowRight size={16} /></button></div><div className="hero-art" aria-hidden="true"><div className="hero-radar-sweep" /><div className="hero-orbit orbit-1" /><div className="hero-orbit orbit-2" /><div className="hero-orbit orbit-3" /><div className="hero-center"><img src="/bantayaso-logo.png" alt="BantayAso Mascot" className="hero-mascot-img" /></div><span className="orbit-dot dot-1" /><span className="orbit-dot dot-2" /><span className="orbit-dot dot-3" /><span className="orbit-dot dot-4" /><div className="hero-floating-pill"><span className="hero-pill-icon"><PawPrint size={13} /></span><span><strong>{summary?.dogs_today || 0} {summary?.dogs_today === 1 ? 'dog' : 'dogs'}</strong> detected today</span></div></div></div>
            <div className="stats-grid"><div className="stat-card stat-card-green"><div className="stat-top"><span className="stat-trend">Today</span></div><strong>{summary?.dogs_today || 0}</strong><span>Dog counts today</span><small>Across recorded detection events</small></div><div className="stat-card stat-card-blue"><div className="stat-top"><span className="stat-trend">Monitoring</span></div><strong>{summary?.active_cameras || 0}<em> / {summary?.total_cameras || 0}</em></strong><span>Active CCTV cameras</span><small>Devices connected to the network</small></div><div className="stat-card stat-card-amber"><div className="stat-top"><span className="stat-trend">Action needed</span></div><strong>{summary?.pending_reviews || 0}</strong><span>Pending reviews</span><small>Detections awaiting verification</small></div><div className="stat-card stat-card-purple"><div className="stat-top"><span className="stat-trend">All areas</span></div><strong>{summary?.locations_monitored || 0}</strong><span>Monitoring zones</span><small>Locations under observation</small></div></div>
            <section className="card activity-card activity-card-full"><div className="card-header"><div><span className="section-kicker">ACTIVITY INSIGHTS</span><h3>Detection activity</h3><p>Peak dog counts across events over the last 7 days</p></div><span className="period-chip"><CalendarDays size={15} /> Last 7 days</span></div><div className="chart-total"><strong>{analytics?.daily.reduce((total, day) => total + day.dogs, 0) || 0}</strong><span>dogs this week</span></div><div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><AreaChart data={analytics?.daily || []} margin={{ top: 10, right: 8, left: -30, bottom: 0 }}><defs><linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#10b981" stopOpacity={0.4} /><stop offset="100%" stopColor="#10b981" stopOpacity={0.0} /></linearGradient></defs><CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 5" vertical={false} /><XAxis dataKey="date" tickFormatter={weekday} tickLine={false} axisLine={false} tick={{ fill: 'var(--muted)', fontSize: 12 }} dy={12} /><YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fill: 'var(--muted)', fontSize: 12 }} /><Tooltip contentStyle={{ border: '1px solid var(--border)', borderRadius: 12, background: 'var(--card)', color: 'var(--text)' }} labelFormatter={value => dateOnly(String(value))} /><Area type="monotone" dataKey="dogs" stroke="#10b981" strokeWidth={3} fill="url(#chartFill)" activeDot={{ r: 6, fill: '#10b981', stroke: '#fff', strokeWidth: 2 }} /></AreaChart></ResponsiveContainer></div></section>
            <section className="card recent-card"><div className="card-header"><div><span className="section-kicker">RECENT EVENTS</span><h3>Latest detections</h3><p>Snapshots and counts from every monitoring zone</p></div><button className="text-button" onClick={() => selectPage('detections')}>View all detections <ArrowRight size={16} /></button></div><DetectionList rows={detections.slice(0, 4)} onOpen={openDetection} onDelete={setDeleteTarget} compact /></section>
          </>}

          {page === 'detections' && <><div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> DETECTION RECORDS</div><h1>{filteredDevice ? `Detections from ${filteredDevice.name}` : "Detection history"}</h1><p>{filteredDevice ? `Showing records from ${filteredDevice.id} at ${filteredDevice.location.name}.` : "Review camera activity from every monitoring zone."}</p></div><div className="heading-actions">{deviceFilter !== "all" && <button className="outline-button" onClick={() => { setDeviceFilter("all"); setLocationFilter("all") }}><ArrowRight size={16} /> All detections</button>}{deviceFilter === "all" && <button className="danger-button" title="Delete all detections" onClick={() => setDeleteTarget('all')} disabled={working || detections.length === 0}><Trash2 size={17} /> Delete all</button>}<button className="outline-button" onClick={exportCsv}><ArrowDownToLine size={17} /> Export CSV</button></div></div><div className="records-summary"><div><span>Shown detections</span><strong>{filtered.length}</strong></div><div><span>Awaiting review</span><strong>{filtered.filter(row => row.review_status === "pending").length}</strong></div><div><span>Dog counts across events</span><strong>{filtered.reduce((sum, row) => sum + row.dog_count, 0)}</strong></div></div><section className="card records-card"><div className="filter-bar"><label className="search-field"><Search size={18} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search detection, camera or location" /></label><CustomDropdown icon={SlidersHorizontal} ariaLabel="Filter by status" value={statusFilter} options={[{ value: 'all', label: 'All statuses' }, { value: 'pending', label: 'Pending' }, { value: 'reviewed', label: 'Reviewed' }, { value: 'flagged', label: 'Flagged' }]} onChange={val => setStatusFilter(val)} /><CustomDropdown icon={MapPin} ariaLabel="Filter by location" value={filteredDevice ? filteredDevice.location.id : locationFilter} disabled={!!filteredDevice} options={[{ value: 'all', label: 'All locations' }, ...locations.map(loc => ({ value: loc.id, label: loc.name }))]} onChange={val => setLocationFilter(val === 'all' ? 'all' : Number(val))} /><CustomDropdown icon={Dog} ariaLabel="Filter by group size" value={groupFilter} options={[{ value: 'all', label: 'All group sizes' }, { value: 'packs', label: `Packs only (${packSize}+ dogs)` }]} onChange={val => setGroupFilter(val === 'packs' ? 'packs' : 'all')} /></div><div className="table-labels"><span className="table-label-thumb" /><span>CAPTURE / EVENT</span><span>TIME RECORDED</span><span>REVIEW STATUS</span><span className="table-label-action" /></div><DetectionList rows={filtered} onOpen={openDetection} onDelete={setDeleteTarget} emptyMessage={filteredDevice ? `No detections have been recorded for ${filteredDevice.name} yet.` : undefined} /><div className="records-footer">Showing {filtered.length} of {detections.length} detections <span>New reports appear within a few seconds</span></div></section></>}

          {page === 'cameras' && (selectedCamera ? <CameraDetail device={selectedCamera} rows={selectedCameraRows} onBack={() => setSelectedCameraId(null)} onViewHistory={() => openCameraDetections(selectedCamera)} onOpen={openDetection} onDelete={setDeleteTarget} /> : <><div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> DEVICE NETWORK</div><h1>CCTV cameras</h1><p>Select a camera to view its detections and snapshots.</p></div><button className="primary-button" onClick={() => setAddOpen(true)}><Plus size={17} /> Add camera</button></div><div className="camera-summary"><div><strong>{summary?.active_cameras || 0} online</strong><span>camera connections</span></div><div><strong>{(summary?.total_cameras || 0) - (summary?.active_cameras || 0)} offline</strong><span>not connected</span></div><div><strong>{locations.length} zones</strong><span>under observation</span></div></div><div className="camera-grid">{devices.map(device => { const latest = detections.find(row => row.device_id === device.id && row.snapshot_path); return <article className="camera-card card" key={device.id} role="button" tabIndex={0} aria-label={`Open camera ${device.name}`} onClick={() => openCameraDetails(device)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openCameraDetails(device) } }}><div className="camera-preview">{latest?.snapshot_path ? <img src={api.snapshot(latest.snapshot_path)} alt={`Latest snapshot at ${device.location.name}`} /> : <div className="camera-no-preview"><Camera size={32} /><span>No captures yet</span></div>}<span className="camera-preview-label"><Radio size={13} /> {latest ? 'LATEST SNAPSHOT' : 'AWAITING CAPTURE'}</span></div><div className="camera-info"><div><span className="camera-id">{device.id}</span><span className="camera-pills">{hotspotLocationIds.has(device.location.id) && <span className="hotspot-badge" title="This zone is over the hotspot limit"><Flame size={12} /> Hotspot</span>}<StatusPill status={device.status} /></span></div><h3>{device.name}</h3><p><MapPin size={15} /> {device.location.name}, {device.location.barangay}</p><div className="camera-meta"><span><Clock3 size={14} /> {device.last_seen ? `Last signal ${dateTime(device.last_seen)}` : 'No signal yet'}</span><span><Eye size={14} /> {detections.filter(row => row.device_id === device.id).length} events</span><span className="camera-open-hint">Open camera <ArrowRight size={14} /></span></div></div></article> })}</div></>)}

          {page === 'analytics' && detections.length === 0 && <EmptyAnalytics />}
          {page === 'analytics' && detections.length > 0 && <AnalyticsPage detections={detections} summary={summary} report={report} packSize={packSize} hotspots={hotspots} range={reportRange} onRange={setReportRange} onExportRecords={exportCsv} onExportReport={exportReport} onSettings={() => selectPage('settings')} />}

          {page === 'settings' && <><div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> SYSTEM PREFERENCES</div><h1>Settings</h1><p>Control how the monitoring workspace looks and updates.</p></div></div><div className="settings-layout"><section className="card settings-card"><div className="settings-row"><div className="settings-icon"><Sun size={20} /></div><div><strong>Appearance</strong><p>Choose the display mode that works for you.</p></div><button className="outline-button" onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>{theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}{theme === 'light' ? 'Dark mode' : 'Light mode'}</button></div><div className="settings-row"><div className="settings-icon"><RefreshCw size={20} /></div><div><strong>Live updates</strong><p>New reports appear within a few seconds; all data refreshes every 15 seconds.</p></div><span className="setting-value"><span className="tiny-dot" /> Active</span></div><div className="settings-row"><div className="settings-icon"><Dog size={20} /></div><div><strong>Pack size</strong><p>Dogs seen together for 2 seconds or more that count as a pack.</p></div><div className="hotspot-settings"><label><span>Dogs</span><input type="number" min={2} max={20} value={packSize} onChange={event => { const value = Math.round(Number(event.target.value)); if (value >= 2 && value <= 20) setPackSize(value) }} /></label></div></div><div className="settings-row"><div className="settings-icon"><Flame size={20} /></div><div><strong>Hotspot alerts</strong><p>Flag a zone, and send one notice per zone per day, when it reaches this limit.</p></div><div className="hotspot-settings"><label><span>Count</span><select value={hotspotSettings.basis} onChange={event => { const basis: HotspotBasis = event.target.value === 'dogs' ? 'dogs' : 'packs'; setHotspotSettings(current => basis === current.basis ? current : basis === 'dogs' ? { basis, windowHours: 24, threshold: 5 } : { ...DEFAULT_HOTSPOT }) }}><option value="packs">Pack sightings</option><option value="dogs">Dogs</option></select></label><label><span>{hotspotSettings.basis === 'dogs' ? 'Dogs' : 'Packs'}</span><input type="number" min={1} max={1000} value={hotspotSettings.threshold} onChange={event => { const value = Math.round(Number(event.target.value)); if (value >= 1 && value <= 1000) setHotspotSettings(current => ({ ...current, threshold: value })) }} /></label><label><span>Within</span><select value={hotspotSettings.windowHours} onChange={event => setHotspotSettings(current => ({ ...current, windowHours: Number(event.target.value) }))}>{WINDOW_OPTIONS.map(hours => <option key={hours} value={hours}>{windowLabel(hours)}</option>)}</select></label></div></div><div className="settings-row"><div className="settings-icon"><ShieldCheck size={20} /></div><div><strong>Scenario mode</strong><p>Generated snapshots let you practice the review flow without a live camera.</p></div><span className="setting-value">Available</span></div></section><section className="card setup-card"><div className="setup-heading"><span className="settings-icon"><Camera size={22} /></span><div><span className="section-kicker">RECORD FLOW</span><h3>What a scenario creates</h3></div></div><p>Choose a camera and dog count through Simulate a scenario. The resulting still snapshot appears in Detection history with its location, time, and review status.</p><div className="flow-note"><Camera size={18} /><span>Camera → snapshot → detection record → operator review</span></div></section></div></>}
        </>}
      </div>
      <footer className="workspace-footer">
        <div>
          <span>BantayAso LGU Dog Monitoring System</span>
        </div>
        <div>
          <span className="footer-status"><span className="tiny-dot" /> System Active</span>
          <span className="footer-dot">•</span>
          <span>Auto-refresh active (15s)</span>
        </div>
      </footer>
    </main>

    {scenarioOpen && <div className="modal-backdrop modal-centered" onMouseDown={event => { if (!working && event.target === event.currentTarget) setScenarioOpen(false) }}>
      <form className="add-modal scenario-modal" role="dialog" aria-modal="true" aria-labelledby="scenario-title" onSubmit={event => { event.preventDefault(); void simulate() }}>
        <div className="modal-title"><div><span className="section-kicker">CREATE ONE EXAMPLE EVENT</span><h2 id="scenario-title">Simulate a scenario</h2><p>Choose a camera and dog count. One still snapshot will be saved to Detection history.</p></div><button type="button" className="icon-button" aria-label="Close scenario" disabled={working} onClick={() => setScenarioOpen(false)}><X size={20} /></button></div>
        <label>Camera and monitoring zone<select required value={scenarioDevice} onChange={event => setScenarioDevice(event.target.value)}>{devices.map(device => <option key={device.id} value={device.id}>{device.name} · {device.location.name}</option>)}</select></label>
        <fieldset className="scenario-count"><legend>Dogs in this scenario</legend><div>{[1, 2, 3, 4].map(count => <button type="button" key={count} className={scenarioDogs === count ? 'active' : ''} aria-pressed={scenarioDogs === count} onClick={() => setScenarioDogs(count)}>{count}</button>)}</div></fieldset>
        <p className="modal-hint">This creates a generated snapshot for review. It is not a live video feed.</p>
        <div className="modal-actions"><button type="button" className="outline-button" disabled={working} onClick={() => setScenarioOpen(false)}>Cancel</button><button type="submit" className="primary-button" disabled={working || !scenarioDevice}><Plus size={17} /> {working ? 'Creating…' : 'Create scenario'}</button></div>
      </form>
    </div>}

    {selected && <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setSelected(null) }}><aside className="detail-drawer" role="dialog" aria-modal="true" aria-label="Detection details">
      <div className="drawer-header"><div><span className="section-kicker">DETECTION DETAILS</span><h2>{selected.id}</h2></div><div className="drawer-header-actions"><button className="icon-button danger-icon" title="Delete detection" aria-label="Delete detection" disabled={working} onClick={() => setDeleteTarget(selected)}><Trash2 size={19} /></button><button className="icon-button" aria-label="Close details" onClick={() => setSelected(null)}><X size={20} /></button></div></div>
      <div className="drawer-image">{selected.snapshot_path ? <img src={api.snapshot(selected.snapshot_path)} alt={`CCTV snapshot from ${selected.location.name}`} /> : <Camera size={44} />}<span>{selected.source === 'camera' ? 'CAMERA SNAPSHOT' : 'SCENARIO SNAPSHOT'}</span></div>
      <div className="drawer-body"><div className="drawer-result"><span className="stat-icon green"><Dog size={24} /></span><div><strong>{detectionHeading(selected)}</strong><p>{Math.round(selected.confidence * 100)}% confidence · {selected.source === 'simulator' ? 'Scenario' : 'Camera'} source</p></div><StatusPill status={selected.review_status} /></div>
        <div className="detail-fields"><div><span>LOCATION</span><strong>{selected.location.name}</strong><small>Barangay {selected.location.barangay}</small></div><div><span>CAMERA</span><strong>{selected.device.name}</strong><small>{selected.device_id}</small></div><div><span>RECORDED</span><strong>{dateTime(selected.timestamp)}</strong><small>Philippine time</small></div><div><span>REVIEW STATUS</span><strong>{selected.review_status.charAt(0).toUpperCase() + selected.review_status.slice(1)}</strong><small>Operator verification</small></div>
          {selected.source === 'camera' && <><div><span>EVENT STATE</span><strong>{selected.event_state === 'active' ? 'Active' : 'Closed'}</strong><small>Closes after the scene is clear</small></div><div><span>PEOPLE OBSERVED</span><strong>{selected.person_count}</strong><small>Maximum during this event</small></div>{selected.dog_count > 0 && <><div><span>DOGS TOGETHER</span><strong>{groupSize(selected)}{isPack(selected, packSize) ? ' (pack)' : ''}</strong><small>{selected.dogs_together !== null ? 'Most dogs seen together for 2 seconds or more' : 'Peak count; this record has no sustained count'}</small></div><div><span>EVENT LENGTH</span><strong>{selected.duration_s ?? 0} seconds</strong><small>{selected.track_id !== null ? `Track #${selected.track_id}` : 'One camera activity period'}</small></div><div><span>DOGS IN SNAPSHOT</span><strong>{selected.snapshot_dog_count ?? 'Not recorded'}</strong><small>Boxes in the saved image</small></div><div><span>{selected.track_id !== null ? 'TRACKED SIGHTINGS' : 'PEAK DOGS OBSERVED'}</span><strong>{selected.dog_count}</strong><small>{selected.track_id !== null ? 'Legacy track count' : 'Most dogs in any single frame'}</small></div></>}</>}
        </div><div className="drawer-note"><ShieldCheck size={18} /><p>{selected.source === 'camera' ? selected.dog_count ? 'A real camera event. Counts show what the camera saw; they do not show whether the dogs have owners.' : 'A person observation from the trained model.' : 'Scenario records use generated still snapshots. They are not live video.'}</p></div></div>
      <div className="drawer-actions"><button className="outline-button" disabled={working} onClick={() => void updateReview(selected.id, 'flagged')}><Flag size={17} /> Flag event</button><button className="primary-button" disabled={working} onClick={() => void updateReview(selected.id, 'reviewed')}><Check size={17} /> Mark reviewed</button></div>
    </aside></div>}

    {deleteTarget && <div className="modal-backdrop modal-centered confirm-backdrop" onMouseDown={event => { if (!working && event.target === event.currentTarget) setDeleteTarget(null) }}><div className="confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="confirm-delete-title"><div className="confirm-header"><div className="confirm-header-left"><span className="confirm-icon" aria-hidden="true"><AlertTriangle size={20} strokeWidth={2.2} /></span><div><span className="confirm-eyebrow">CONFIRM ACTION</span><h2 id="confirm-delete-title">{deleteTarget === 'all' ? 'Delete all detections?' : 'Delete detection?'}</h2></div></div><button type="button" className="icon-button" aria-label="Close dialog" disabled={working} onClick={() => setDeleteTarget(null)}><X size={18} /></button></div><p>{deleteTarget === 'all' ? <>Are you sure you want to delete all <strong>{detections.length}</strong> detection records? All stored snapshots will be permanently removed, while your cameras and monitoring zones will remain saved.</> : <>Are you sure you want to delete <code className="confirm-id">{deleteTarget.id}</code>? The detection record and its captured snapshot will be permanently removed.</>}</p><div className="modal-actions"><button type="button" className="outline-button" disabled={working} onClick={() => setDeleteTarget(null)}>Cancel</button><button type="button" className="danger-button solid" disabled={working} onClick={() => void confirmDelete()}><Trash2 size={16} /> {working ? 'Deleting…' : deleteTarget === 'all' ? 'Delete all' : 'Delete detection'}</button></div></div></div>}
    {addOpen && <div className="modal-backdrop modal-centered" onMouseDown={event => { if (event.target === event.currentTarget) setAddOpen(false) }}>
      <form className="add-modal" onSubmit={createDevice}>
        <div className="modal-title"><div><span className="section-kicker">DEVICE REGISTRATION</span><h2>Add CCTV camera</h2><p>Give the camera a monitoring zone so detections have a location.</p></div><button type="button" className="icon-button" aria-label="Close" onClick={() => setAddOpen(false)}><X size={20} /></button></div>
        <label>Camera ID<input required minLength={3} maxLength={64} pattern="[A-Za-z0-9_-]+" value={deviceForm.id} onChange={event => setDeviceForm({ ...deviceForm, id: event.target.value })} placeholder="e.g. CAM-002" /></label>
        <label>Camera name<input required minLength={2} maxLength={120} value={deviceForm.name} onChange={event => setDeviceForm({ ...deviceForm, name: event.target.value })} placeholder="e.g. Market Entrance" /></label>
        <div className="zone-choice-header"><strong>Monitoring zone</strong><span>Where is this camera installed?</span></div>
        <div className="zone-switch" role="group" aria-label="Monitoring zone choice"><button type="button" className={!useNewZone ? 'active' : ''} aria-pressed={!useNewZone} onClick={() => setUseNewZone(false)}>Use existing zone</button><button type="button" className={useNewZone ? 'active' : ''} aria-pressed={useNewZone} onClick={() => setUseNewZone(true)}><Plus size={15} /> Create new zone</button></div>
        {useNewZone ? <div className="zone-fields">
          <label>Zone name<input required minLength={2} maxLength={120} value={zoneForm.name} onChange={event => setZoneForm({ ...zoneForm, name: event.target.value })} placeholder="e.g. Public Market" /></label>
          <label>Barangay<input required minLength={2} maxLength={120} value={zoneForm.barangay} onChange={event => setZoneForm({ ...zoneForm, barangay: event.target.value })} placeholder="e.g. Poblacion" /></label>
          <label>Description <span>(optional)</span><input maxLength={500} value={zoneForm.description} onChange={event => setZoneForm({ ...zoneForm, description: event.target.value })} placeholder="e.g. Main entrance facing the street" /></label>
          <p className="zone-hint">The new zone and this camera will be saved together.</p>
        </div> : <label>Choose existing zone<select required value={deviceForm.location_id} onChange={event => setDeviceForm({ ...deviceForm, location_id: Number(event.target.value) })}>{locations.map(location => <option key={location.id} value={location.id}>{location.name} · {location.barangay}</option>)}</select></label>}
        <p className="modal-hint">New cameras start offline. Scenario snapshots do not mark a camera online.</p>
        <div className="modal-actions"><button type="button" className="outline-button" onClick={() => setAddOpen(false)}>Cancel</button><button type="submit" className="primary-button" disabled={working}><Plus size={17} /> {working ? 'Saving…' : 'Add camera'}</button></div>
      </form>
    </div>}
    {toast && <div className="toast"><CheckCircle2 size={19} />{toast}<button aria-label="Dismiss notification" onClick={() => setToast('')}><X size={15} /></button></div>}
  </div></PackSizeContext.Provider>
}
