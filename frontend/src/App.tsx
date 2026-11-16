import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity, ArrowDownToLine, ArrowRight, Bell, CalendarDays, Camera, Check, CheckCircle2,
  ChevronDown, ChevronRight, Clock3, Dog, Eye, Flag, LayoutDashboard,
  MapPin, Menu, Moon, Plus, Radio, RefreshCw, Search, Settings2, ShieldCheck,
  SlidersHorizontal, Sun, Trash2, Video, Wifi, WifiOff, X, ChartNoAxesCombined, AlertTriangle,
} from 'lucide-react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, type Analytics, type Detection, type Device, type Location, type Summary } from './api'

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

function StatusPill({ status }: { status: string }) {
  return <span className={`status-pill status-${status}`}><span className="status-dot" />{status.charAt(0).toUpperCase() + status.slice(1)}</span>
}

function MapGraphic({ locations, devices, onSelect }: { locations: Location[]; devices: Device[]; onSelect: (id: number) => void }) {
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
    <div className="map-label map-label-one">POBLACION</div><div className="map-label map-label-two">BANCOD</div>
    {locations.map((location, index) => <button key={location.id} className={`map-pin ${devices.some(d => d.location.id === location.id && d.status === 'online') ? 'is-online' : 'is-offline'}`} style={{ left: `${spots[index % spots.length].x}%`, top: `${spots[index % spots.length].y}%` }} title={location.name} onClick={() => onSelect(location.id)}><Camera size={15} /></button>)}
    <span className="map-caption">Indang, Cavite · Approximate monitoring zones</span>
  </div>
}

function DetectionList({ rows, onOpen, onDelete, compact = false }: { rows: Detection[]; onOpen: (row: Detection) => void; onDelete: (row: Detection) => void; compact?: boolean }) {
  return <div className={`detection-list ${compact ? 'compact' : ''}`}>
    {rows.length === 0 ? <div className="empty-state"><Camera size={26} /><strong>No detections to show</strong><span>A snapshot, count, and time will appear here after the first event. Check filters if records already exist.</span></div> : rows.map(row => <div className="detection-entry" key={row.id}>
      <button className="detection-row" onClick={() => onOpen(row)}>
        <div className="capture-thumb">{row.snapshot_path ? <img src={api.snapshot(row.snapshot_path)} alt={`CCTV snapshot from ${row.location.name}`} /> : <Camera size={22} />}</div>
        <div className="detection-main"><strong>{row.dog_count} {row.dog_count === 1 ? 'dog' : 'dogs'} detected</strong><span><MapPin size={13} /> {row.location.name} <i /> {row.device_id}</span></div>
        <div className="detection-time"><strong>{timeOnly(row.timestamp)}</strong><span>{dateOnly(row.timestamp)}</span></div>
        <StatusPill status={row.review_status} />
        <span className="row-action-space" />
      </button>
      <button className="detection-delete" title={row.review_status === 'reviewed' ? `Delete ${row.id}` : 'Mark as Reviewed before deleting'} aria-label={row.review_status === 'reviewed' ? `Delete detection ${row.id}` : `Review detection ${row.id} before deleting`} disabled={row.review_status !== 'reviewed'} onClick={() => onDelete(row)}><Trash2 size={16} /></button>
    </div>)}
  </div>
}

function EmptyOverview({ device, onCameras }: { device: Device | undefined; onCameras: () => void }) {
  return <>
    <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> GETTING STARTED</div><h1>Your monitoring workspace</h1><p>No detections have been recorded yet. Start with the single example camera below.</p></div></div>
    <section className="start-hero card"><div className="start-copy"><span className="start-step">START HERE · 1 EXAMPLE CAMERA</span><h2>See what happens after<br />a camera detects a dog.</h2><p>Choose <strong>Simulate a scenario</strong> in the header to create one snapshot. Its dog count, time, and monitoring zone will appear here for review.</p><div className="start-actions"><button className="outline-button" onClick={onCameras}><Camera size={17} /> View camera</button></div><small>Scenarios create still snapshots. There is no live video feed.</small></div><div className="example-camera"><div className="example-camera-top"><span>EXAMPLE CAMERA</span><span className="example-id">{device?.id || 'CAM-001'}</span></div><div className="example-camera-frame"><Camera size={42} strokeWidth={1.5} /><span>No capture yet</span></div><div className="example-camera-bottom"><div><strong>{device?.name || 'Example camera'}</strong><span><MapPin size={13} /> {device?.location.name || 'No location registered'}</span></div><StatusPill status={device?.status || 'offline'} /></div></div></section>
    <div className="start-metrics"><div><strong>0</strong><span>Dogs detected</span></div><div><strong>0</strong><span>Snapshots received</span></div><div><strong>0</strong><span>Events to review</span></div></div>
    <section className="workflow-card card"><div className="card-header"><div><span className="section-kicker">HOW IT WORKS</span><h3>From camera to dashboard</h3><p>A scenario follows the same record flow as a future camera event.</p></div></div><div className="workflow-steps"><div><span className="workflow-icon"><Camera size={20} /></span><em>01</em><strong>Choose a camera</strong><p>Select its monitoring zone and dog count.</p></div><ArrowRight className="workflow-arrow" size={18} /><div><span className="workflow-icon"><Activity size={20} /></span><em>02</em><strong>Create a snapshot</strong><p>One still image and timestamp are generated.</p></div><ArrowRight className="workflow-arrow" size={18} /><div><span className="workflow-icon"><ShieldCheck size={20} /></span><em>03</em><strong>Save the record</strong><p>The count and image are stored together.</p></div><ArrowRight className="workflow-arrow" size={18} /><div><span className="workflow-icon"><LayoutDashboard size={20} /></span><em>04</em><strong>Review here</strong><p>Inspect and mark the event reviewed.</p></div></div></section>
  </>
}

function EmptyAnalytics() {
  return <><div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> MONITORING INSIGHTS</div><h1>Activity analytics</h1><p>Charts and location trends will appear after detections arrive.</p></div></div><section className="analytics-empty card"><ChartNoAxesCombined size={34} /><h2>No activity to chart yet</h2><p>Choose <strong>Simulate a scenario</strong> in the header to create the first snapshot and data point.</p></section></>
}

export default function App() {
  const [page, setPage] = useState<Page>('overview')
  const [theme, setTheme] = useState<Theme>(() => localStorage.getItem('straywatch-theme') === 'dark' ? 'dark' : 'light')
  const [summary, setSummary] = useState<Summary | null>(null)
  const [detections, setDetections] = useState<Detection[]>([])
  const [devices, setDevices] = useState<Device[]>([])
  const [locations, setLocations] = useState<Location[]>([])
  const [analytics, setAnalytics] = useState<Analytics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [locationFilter, setLocationFilter] = useState<number | 'all'>('all')
  const [selected, setSelected] = useState<Detection | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Detection | 'all' | null>(null)
  const [addOpen, setAddOpen] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [sidebarExpanded, setSidebarExpanded] = useState(() => localStorage.getItem('straywatch-sidebar-expanded') === 'true')
  const [scenarioOpen, setScenarioOpen] = useState(false)
  const [scenarioDevice, setScenarioDevice] = useState('')
  const [scenarioDogs, setScenarioDogs] = useState(2)
  const [toast, setToast] = useState('')
  const [working, setWorking] = useState(false)
  const [deviceForm, setDeviceForm] = useState({ id: '', name: '', location_id: 1 })
  const [useNewZone, setUseNewZone] = useState(false)
  const [zoneForm, setZoneForm] = useState({ name: '', barangay: '', description: '' })

  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem('straywatch-theme', theme) }, [theme])
  useEffect(() => { localStorage.setItem('straywatch-sidebar-expanded', String(sidebarExpanded)) }, [sidebarExpanded])
  useEffect(() => { if (toast) { const timer = window.setTimeout(() => setToast(''), 4000); return () => clearTimeout(timer) } }, [toast])

  const refresh = useCallback(async (first = false) => {
    if (first) setLoading(true)
    try {
      const [s, ds, dv, loc, an] = await Promise.all([api.summary(), api.detections(), api.devices(), api.locations(), api.analytics()])
      setSummary(s); setDetections(ds); setDevices(dv); setLocations(loc); setAnalytics(an); setError('')
      setSelected(current => current ? ds.find(item => item.id === current.id) || null : null)
    } catch (issue) { setError(issue instanceof Error ? issue.message : 'Could not connect to the local service') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { void refresh(true); const timer = window.setInterval(() => { void refresh() }, 15000); return () => clearInterval(timer) }, [refresh])

  const filtered = useMemo(() => detections.filter(row => {
    const text = `${row.id} ${row.device_id} ${row.device.name} ${row.location.name} ${row.location.barangay}`.toLowerCase()
    return text.includes(query.toLowerCase()) && (statusFilter === 'all' || row.review_status === statusFilter) && (locationFilter === 'all' || row.location.id === locationFilter)
  }), [detections, query, statusFilter, locationFilter])

  const alertCount = summary?.pending_reviews || 0
  const unreviewedCount = detections.filter(row => row.review_status !== 'reviewed').length
  const nowLabel = new Intl.DateTimeFormat('en-PH', { timeZone: 'Asia/Manila', weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }).format(new Date())

  async function simulate() {
    setWorking(true)
    try {
      const event = await api.simulate(scenarioDevice || devices[0]?.id, scenarioDogs)
      setScenarioOpen(false)
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
        setToast(`Cleared ${result.deleted} detection${result.deleted === 1 ? '' : 's'} and their snapshots`)
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
    const header = 'Detection ID,Timestamp,Device,Location,Dog count,Confidence,Review status\n'
    const body = filtered.map(row => [row.id, row.timestamp, row.device_id, row.location.name, row.dog_count, row.confidence, row.review_status].map(value => `"${String(value).replaceAll('"', '""')}"`).join(',')).join('\n')
    const url = URL.createObjectURL(new Blob([header + body], { type: 'text/csv' }))
    const link = document.createElement('a'); link.href = url; link.download = 'straywatch-detections.csv'; link.click(); URL.revokeObjectURL(url)
  }

  const selectPage = (next: Page) => { setPage(next); setMobileOpen(false); setQuery('') }

  return <div className="app-shell">
    {mobileOpen && <button className="sidebar-scrim" aria-label="Close menu" onClick={() => setMobileOpen(false)} />}
    <aside className={`sidebar ${sidebarExpanded ? 'expanded' : ''} ${mobileOpen ? 'mobile-open' : ''}`} onClick={event => {
      if (window.matchMedia('(max-width: 760px)').matches) return
      // Nav buttons (and the gaps between them) navigate only; every other part of the sidebar toggles it.
      if ((event.target as Element).closest('.nav-list')) return
      setSidebarExpanded(value => !value)
    }}>
      <button className="brand" type="button" title={mobileOpen ? 'Close menu' : sidebarExpanded ? 'Collapse sidebar' : 'Expand sidebar'} aria-label={mobileOpen ? 'Close menu' : sidebarExpanded ? 'Collapse sidebar' : 'Expand sidebar'} aria-expanded={mobileOpen || sidebarExpanded} onClick={() => { if (window.matchMedia('(max-width: 760px)').matches) setMobileOpen(false) }}><span className="brand-icon"><Dog size={25} strokeWidth={2.5} /></span><span className="brand-name"><strong>StrayWatch<span>.</span></strong><small>LGU MONITORING SYSTEM</small></span></button>
      <div className="workspace-tag" title="Indang LGU"><span className="workspace-logo">I</span><span><strong>Indang LGU</strong><small>Municipal dashboard</small></span></div>
      <div className="nav-section-label">WORKSPACE</div>
      <nav className="nav-list" aria-label="Main navigation">{navigation.slice(0, 4).map(item => <button key={item.id} title={item.label} aria-label={item.label} aria-current={page === item.id ? 'page' : undefined} className={`nav-item ${page === item.id ? 'active' : ''}`} onClick={() => selectPage(item.id)}><item.icon size={19} strokeWidth={2} /><span>{item.label}</span>{item.id === 'detections' && alertCount > 0 && <em>{alertCount}</em>}</button>)}</nav>
      <div className="nav-section-label nav-section-second">SYSTEM</div>
      <nav className="nav-list"><button title="Settings" aria-label="Settings" aria-current={page === 'settings' ? 'page' : undefined} className={`nav-item ${page === 'settings' ? 'active' : ''}`} onClick={() => selectPage('settings')}><Settings2 size={19} /><span>Settings</span></button></nav>
      <div className="sidebar-spacer" />
      <div className="sidebar-profile" title="LGU Operator"><span className="profile-avatar">LG</span><span><strong>LGU Operator</strong><small>Administrator</small></span></div>
    </aside>

    <main className="main-panel">
      <header className="topbar"><div className="topbar-left"><button className="icon-button mobile-menu" aria-label="Open menu" onClick={() => setMobileOpen(true)}><Menu size={21} /></button><span className="breadcrumb-root">Workspace</span><ChevronRight size={16} /><strong>{navigation.find(item => item.id === page)?.label}</strong></div><div className="topbar-actions"><div className={'live-indicator ' + (error ? 'offline' : '')}><span /> {error ? 'Service offline' : 'Service connected'}</div><button className="primary-button scenario-trigger" aria-label="Simulate a scenario" disabled={working || devices.length === 0 || !!error} onClick={() => { setScenarioDevice(devices[0]?.id || ''); setScenarioOpen(true) }}><Plus size={16} /><span>Simulate a scenario</span></button><button className="icon-button" title="Toggle dark mode" aria-label="Toggle dark mode" onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>{theme === 'light' ? <Moon size={19} /> : <Sun size={19} />}</button>{alertCount > 0 && <button className="icon-button notification-button" title={`${alertCount} pending reviews`} aria-label={`${alertCount} pending reviews`} onClick={() => selectPage('detections')}><Bell size={19} /><i /></button>}<span className="top-avatar">LG</span></div></header>

      <div className="content">
        {error && <div className="error-banner"><WifiOff size={18} /><span>{error}</span><button onClick={() => void refresh()}>Retry</button></div>}
        {loading && !summary ? <div className="loading-state"><RefreshCw className="spin" size={28} /><strong>Loading monitoring data…</strong></div> : <>
          {page === 'overview' && detections.length === 0 && <EmptyOverview device={devices[0]} onCameras={() => selectPage('cameras')} />}
          {page === 'overview' && detections.length > 0 && <>
            <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> DETECTION OVERVIEW</div><h1>Good day, Operator <span className="heading-wave">✳</span></h1><p>Here's what's happening across your monitored areas today.</p></div><div className="heading-actions"><span className="date-chip"><CalendarDays size={16} />{nowLabel}</span></div></div>
            <div className="hero-card"><div className="hero-content"><div className="hero-badge"><Radio size={14} /> DETECTION RECORDS</div><h2>Keeping our streets<br />safer, one sighting<br />at a time.</h2><p>Review incoming detection records, snapshots, and locations in one place.</p><button onClick={() => selectPage('detections')}>Explore detections <ArrowRight size={16} /></button></div><div className="hero-art" aria-hidden="true"><div className="hero-orbit orbit-1" /><div className="hero-orbit orbit-2" /><div className="hero-orbit orbit-3" /><div className="hero-center"><Dog size={73} strokeWidth={1.3} /></div><span className="orbit-dot dot-1" /><span className="orbit-dot dot-2" /><span className="orbit-dot dot-3" /><div className="hero-floating"><span><Activity size={17} /></span><div><strong>{summary?.dogs_today || 0} dogs</strong><small>Spotted today</small></div></div></div></div>
            <div className="stats-grid"><div className="stat-card"><div className="stat-top"><span className="stat-icon green"><Dog size={21} /></span><span className="stat-trend"><ArrowRight size={13} /> Today</span></div><strong>{summary?.dogs_today || 0}</strong><span>Dogs detected today</span><small>Across recorded detection events</small></div><div className="stat-card"><div className="stat-top"><span className="stat-icon blue"><Camera size={20} /></span><span className="stat-trend positive"><span className="tiny-dot" /> Monitoring</span></div><strong>{summary?.active_cameras || 0}<em> / {summary?.total_cameras || 0}</em></strong><span>Active CCTV cameras</span><small>Devices connected to the network</small></div><div className="stat-card"><div className="stat-top"><span className="stat-icon amber"><ShieldCheck size={21} /></span><span className="stat-trend"><Clock3 size={13} /> Action needed</span></div><strong>{summary?.pending_reviews || 0}</strong><span>Pending reviews</span><small>Detections awaiting verification</small></div><div className="stat-card"><div className="stat-top"><span className="stat-icon purple"><MapPin size={21} /></span><span className="stat-trend">Indang, Cavite</span></div><strong>{summary?.locations_monitored || 0}</strong><span>Monitoring zones</span><small>Locations under observation</small></div></div>
            <div className="dashboard-grid"><section className="card activity-card"><div className="card-header"><div><span className="section-kicker">ACTIVITY INSIGHTS</span><h3>Detection activity</h3><p>Dog sightings recorded over the last 7 days</p></div><span className="period-chip"><CalendarDays size={15} /> Last 7 days</span></div><div className="chart-total"><strong>{analytics?.daily.reduce((total, day) => total + day.dogs, 0) || 0}</strong><span>dogs this week</span></div><div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><AreaChart data={analytics?.daily || []} margin={{ top: 10, right: 8, left: -30, bottom: 0 }}><defs><linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#43ad79" stopOpacity={0.23} /><stop offset="100%" stopColor="#43ad79" stopOpacity={0} /></linearGradient></defs><CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 5" vertical={false} /><XAxis dataKey="date" tickFormatter={weekday} tickLine={false} axisLine={false} tick={{ fill: 'var(--muted)', fontSize: 12 }} dy={12} /><YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fill: 'var(--muted)', fontSize: 12 }} /><Tooltip contentStyle={{ border: '1px solid var(--border)', borderRadius: 12, background: 'var(--card)', color: 'var(--text)' }} labelFormatter={value => dateOnly(String(value))} /><Area type="monotone" dataKey="dogs" stroke="#1f9d6c" strokeWidth={3} fill="url(#chartFill)" activeDot={{ r: 6, fill: '#13865d', stroke: '#fff', strokeWidth: 3 }} /></AreaChart></ResponsiveContainer></div></section><section className="card zones-card"><div className="card-header"><div><span className="section-kicker">LOCATION COVERAGE</span><h3>Monitoring zones</h3><p>Camera locations across the municipality</p></div><button className="subtle-icon" title="View cameras" onClick={() => selectPage('cameras')}><ArrowRight size={18} /></button></div><MapGraphic locations={locations} devices={devices} onSelect={id => { setLocationFilter(id); selectPage('detections'); setLocationFilter(id) }} /><div className="map-legend"><span><i className="legend-online" /> Active camera</span><span><i className="legend-offline" /> Offline camera</span></div></section></div>
            <section className="card recent-card"><div className="card-header"><div><span className="section-kicker">RECENT EVENTS</span><h3>Latest detections</h3><p>Snapshots and counts from every monitoring zone</p></div><button className="text-button" onClick={() => selectPage('detections')}>View all detections <ArrowRight size={16} /></button></div><DetectionList rows={detections.slice(0, 4)} onOpen={setSelected} onDelete={setDeleteTarget} compact /></section>
          </>}

          {page === 'detections' && <><div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> DETECTION RECORDS</div><h1>Detection history</h1><p>Review sightings and track activity from every camera.</p></div><div className="heading-actions"><button className="danger-button" title={unreviewedCount > 0 ? 'Review every detection before clearing all' : 'Delete all detections'} onClick={() => setDeleteTarget('all')} disabled={working || detections.length === 0 || unreviewedCount > 0}><Trash2 size={17} /> Clear all</button><button className="outline-button" onClick={exportCsv}><ArrowDownToLine size={17} /> Export CSV</button></div></div><div className="records-summary"><div><span>All detections</span><strong>{detections.length}</strong></div><div><span>Awaiting review</span><strong>{summary?.pending_reviews || 0}</strong></div><div><span>Dogs counted</span><strong>{detections.reduce((sum, row) => sum + row.dog_count, 0)}</strong></div></div>{detections.length > 0 && unreviewedCount > 0 && <div className="review-policy-note"><ShieldCheck size={17} /><span>Only <strong>Reviewed</strong> detections can be deleted. Review the remaining {unreviewedCount} record{unreviewedCount === 1 ? '' : 's'} to enable Clear all.</span></div>}<section className="card records-card"><div className="filter-bar"><label className="search-field"><Search size={18} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search detection, camera or location" /></label><label className="select-field"><SlidersHorizontal size={17} /><select aria-label="Filter by status" value={statusFilter} onChange={event => setStatusFilter(event.target.value)}><option value="all">All statuses</option><option value="pending">Pending</option><option value="reviewed">Reviewed</option><option value="flagged">Flagged</option></select><ChevronDown size={15} /></label><label className="select-field"><MapPin size={17} /><select aria-label="Filter by location" value={locationFilter} onChange={event => setLocationFilter(event.target.value === 'all' ? 'all' : Number(event.target.value))}><option value="all">All locations</option>{locations.map(location => <option key={location.id} value={location.id}>{location.name}</option>)}</select><ChevronDown size={15} /></label></div><div className="table-labels"><span>CAPTURE / EVENT</span><span>TIME RECORDED</span><span>REVIEW STATUS</span></div><DetectionList rows={filtered} onOpen={setSelected} onDelete={setDeleteTarget} /><div className="records-footer">Showing {filtered.length} of {detections.length} detections <span>Updates automatically every 15 seconds</span></div></section></>}

          {page === 'cameras' && <><div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> DEVICE NETWORK</div><h1>CCTV cameras</h1><p>Manage connected devices and see where they're monitoring.</p></div><button className="primary-button" onClick={() => setAddOpen(true)}><Plus size={17} /> Add camera</button></div><div className="camera-summary"><div><Wifi size={20} /><strong>{summary?.active_cameras || 0} online</strong><span>camera connections</span></div><div><WifiOff size={20} /><strong>{(summary?.total_cameras || 0) - (summary?.active_cameras || 0)} offline</strong><span>not connected</span></div><div><MapPin size={20} /><strong>{locations.length} zones</strong><span>under observation</span></div></div><div className="camera-grid">{devices.map(device => { const latest = detections.find(row => row.device_id === device.id && row.snapshot_path); return <article className="camera-card card" key={device.id}><div className="camera-preview">{latest?.snapshot_path ? <img src={api.snapshot(latest.snapshot_path)} alt={`Latest snapshot at ${device.location.name}`} /> : <div className="camera-no-preview"><Camera size={32} /><span>No captures yet</span></div>}<span className="camera-preview-label"><Radio size={13} /> {latest ? 'LATEST SNAPSHOT' : 'AWAITING CAPTURE'}</span></div><div className="camera-info"><div><span className="camera-id">{device.id}</span><StatusPill status={device.status} /></div><h3>{device.name}</h3><p><MapPin size={15} /> {device.location.name}, {device.location.barangay}</p><div className="camera-meta"><span><Clock3 size={14} /> {device.last_seen ? `Last signal ${dateTime(device.last_seen)}` : 'No signal yet'}</span><span><Eye size={14} /> {detections.filter(row => row.device_id === device.id).length} events</span></div></div></article> })}</div></>}

          {page === 'analytics' && detections.length === 0 && <EmptyAnalytics />}
          {page === 'analytics' && detections.length > 0 && <><div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> MONITORING INSIGHTS</div><h1>Activity analytics</h1><p>See how dog activity changes across places and time.</p></div><button className="outline-button" onClick={exportCsv}><ArrowDownToLine size={17} /> Export records</button></div><div className="analytics-top"><div className="analytics-highlight card"><span className="section-kicker">TOTAL DOGS OBSERVED</span><strong>{detections.reduce((sum, row) => sum + row.dog_count, 0)}</strong><p>Across {summary?.total_detections || 0} recorded events</p><Dog size={75} /></div><div className="analytics-highlight card"><span className="section-kicker">AVERAGE CONFIDENCE</span><strong>{detections.length ? Math.round(detections.reduce((sum, row) => sum + row.confidence, 0) / detections.length * 100) : 0}%</strong><p>Reported confidence across recorded events</p><Activity size={75} /></div><div className="analytics-highlight card"><span className="section-kicker">REVIEWED EVENTS</span><strong>{detections.filter(row => row.review_status === 'reviewed').length}</strong><p>{summary?.pending_reviews || 0} records waiting for review</p><CheckCircle2 size={75} /></div></div><div className="dashboard-grid analytics-grid"><section className="card activity-card"><div className="card-header"><div><span className="section-kicker">WEEKLY TREND</span><h3>Dog sightings by day</h3><p>Recorded count from all monitoring zones</p></div><span className="period-chip">Last 7 days</span></div><div className="chart-wrap analytics-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={analytics?.daily || []} margin={{ top: 12, right: 8, left: -30, bottom: 0 }}><CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 5" vertical={false} /><XAxis dataKey="date" tickFormatter={weekday} tickLine={false} axisLine={false} tick={{ fill: 'var(--muted)', fontSize: 12 }} dy={12} /><YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fill: 'var(--muted)', fontSize: 12 }} /><Tooltip contentStyle={{ border: '1px solid var(--border)', borderRadius: 12, background: 'var(--card)', color: 'var(--text)' }} /><Area type="monotone" dataKey="dogs" stroke="#1f9d6c" strokeWidth={3} fill="#1f9d6c" fillOpacity={.15} /></AreaChart></ResponsiveContainer></div></section><section className="card location-rank"><div className="card-header"><div><span className="section-kicker">LOCATION BREAKDOWN</span><h3>Activity by zone</h3><p>Total dogs recorded per location</p></div></div><div className="rank-list">{[...(analytics?.by_location || [])].sort((a, b) => b.count - a.count).map((item, index, all) => <div className="rank-row" key={item.location_id}><div><span className="rank-index">{String(index + 1).padStart(2, '0')}</span><strong>{item.name}</strong><span>{item.count} dogs</span></div><div className="rank-track"><span style={{ width: `${all[0].count ? (item.count / all[0].count) * 100 : 0}%` }} /></div></div>)}</div></section></div></>}

          {page === 'settings' && <><div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> SYSTEM PREFERENCES</div><h1>Settings</h1><p>Control how the monitoring workspace looks and updates.</p></div></div><div className="settings-layout"><section className="card settings-card"><div className="settings-row"><div className="settings-icon"><Sun size={20} /></div><div><strong>Appearance</strong><p>Choose the display mode that works for you.</p></div><button className="outline-button" onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>{theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}{theme === 'light' ? 'Dark mode' : 'Light mode'}</button></div><div className="settings-row"><div className="settings-icon"><RefreshCw size={20} /></div><div><strong>Live updates</strong><p>Dashboard data refreshes every 15 seconds.</p></div><span className="setting-value"><span className="tiny-dot" /> Active</span></div><div className="settings-row"><div className="settings-icon"><ShieldCheck size={20} /></div><div><strong>Scenario mode</strong><p>Generated snapshots let you practice the review flow without a live camera.</p></div><span className="setting-value">Available</span></div></section><section className="card setup-card"><div className="setup-heading"><span className="settings-icon"><Camera size={22} /></span><div><span className="section-kicker">RECORD FLOW</span><h3>What a scenario creates</h3></div></div><p>Choose a camera and dog count through Simulate a scenario. The resulting still snapshot appears in Detection history with its location, time, and review status.</p><div className="flow-note"><Camera size={18} /><span>Camera → snapshot → detection record → operator review</span></div></section></div></>}
        </>}
      </div>
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

    {selected && <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setSelected(null) }}><aside className="detail-drawer" role="dialog" aria-modal="true" aria-label="Detection details"><div className="drawer-header"><div><span className="section-kicker">DETECTION DETAILS</span><h2>{selected.id}</h2></div><div className="drawer-header-actions"><button className="icon-button danger-icon" title={selected.review_status === 'reviewed' ? 'Delete detection' : 'Mark as Reviewed before deleting'} aria-label="Delete detection" disabled={selected.review_status !== 'reviewed'} onClick={() => setDeleteTarget(selected)}><Trash2 size={19} /></button><button className="icon-button" aria-label="Close details" onClick={() => setSelected(null)}><X size={20} /></button></div></div><div className="drawer-image">{selected.snapshot_path ? <img src={api.snapshot(selected.snapshot_path)} alt={`CCTV snapshot from ${selected.location.name}`} /> : <Camera size={44} />}<span>SCENARIO SNAPSHOT</span></div><div className="drawer-body"><div className="drawer-result"><span className="stat-icon green"><Dog size={24} /></span><div><strong>{selected.dog_count} {selected.dog_count === 1 ? 'dog' : 'dogs'} detected</strong><p>{Math.round(selected.confidence * 100)}% confidence · {selected.source === 'simulator' ? 'Scenario' : 'Camera'} source</p></div><StatusPill status={selected.review_status} /></div><div className="detail-fields"><div><span>LOCATION</span><strong>{selected.location.name}</strong><small>{selected.location.barangay}, Indang</small></div><div><span>CAMERA</span><strong>{selected.device.name}</strong><small>{selected.device_id}</small></div><div><span>RECORDED</span><strong>{dateTime(selected.timestamp)}</strong><small>Philippine time</small></div><div><span>REVIEW STATUS</span><strong>{selected.review_status.charAt(0).toUpperCase() + selected.review_status.slice(1)}</strong><small>Operator verification</small></div></div><div className="drawer-note"><ShieldCheck size={18} /><p>Scenario records use generated still snapshots. They are not live video.</p></div></div><div className="drawer-actions"><button className="outline-button" disabled={working} onClick={() => void updateReview(selected.id, 'flagged')}><Flag size={17} /> Flag event</button><button className="primary-button" disabled={working} onClick={() => void updateReview(selected.id, 'reviewed')}><Check size={17} /> Mark reviewed</button></div></aside></div>}

    {deleteTarget && <div className="modal-backdrop modal-centered confirm-backdrop" onMouseDown={event => { if (!working && event.target === event.currentTarget) setDeleteTarget(null) }}><div className="confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="confirm-delete-title"><span className="confirm-icon"><AlertTriangle size={24} /></span><h2 id="confirm-delete-title">{deleteTarget === 'all' ? 'Clear all detections?' : 'Delete this detection?'}</h2><p>{deleteTarget === 'all' ? `This will remove all ${detections.length} detection records and their stored snapshots. Cameras and locations will stay.` : `This will remove ${deleteTarget.id} and its stored snapshot.`}</p><div className="modal-actions"><button className="outline-button" disabled={working} onClick={() => setDeleteTarget(null)}>Cancel</button><button className="danger-button solid" disabled={working} onClick={() => void confirmDelete()}><Trash2 size={17} /> {working ? 'Deleting…' : deleteTarget === 'all' ? 'Clear all' : 'Delete detection'}</button></div></div></div>}
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
          <p className="zone-hint">The new zone and this camera will be saved together. Map markers are approximate in this prototype.</p>
        </div> : <label>Choose existing zone<select required value={deviceForm.location_id} onChange={event => setDeviceForm({ ...deviceForm, location_id: Number(event.target.value) })}>{locations.map(location => <option key={location.id} value={location.id}>{location.name} · {location.barangay}</option>)}</select></label>}
        <p className="modal-hint">New cameras start offline. Scenario snapshots do not mark a camera online.</p>
        <div className="modal-actions"><button type="button" className="outline-button" onClick={() => setAddOpen(false)}>Cancel</button><button type="submit" className="primary-button" disabled={working}><Plus size={17} /> {working ? 'Saving…' : 'Add camera'}</button></div>
      </form>
    </div>}
    {toast && <div className="toast"><CheckCircle2 size={19} />{toast}<button aria-label="Dismiss notification" onClick={() => setToast('')}><X size={15} /></button></div>}
  </div>
}
