import { useEffect, useState, useRef } from 'react'
import ZoneEditor from './components/ZoneEditor'
import { DetectionEvent, Camera, Zone, Alert, Incident } from './types'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const navItems = [
  { label: 'Dashboard', icon: 'grid' },
  { label: 'Cameras', icon: 'camera' },
  { label: 'Zones', icon: 'zones' },
  { label: 'Alerts', icon: 'bell' },
  { label: 'Incidents', icon: 'bell' },
  { label: 'ANPR', icon: 'anpr' },
  { label: 'ReID', icon: 'reid' },
  { label: 'Case Files', icon: 'case' },
  { label: 'AI Chat', icon: 'chat' },
  { label: 'Settings', icon: 'settings' },
]

function Icon({ name, className }: { name: string; className?: string }) {
  const icons: Record<string, JSX.Element> = {
    grid: <g strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" fill="none" stroke="currentColor"><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><path d="M5 12h2M9 10v4M15 12h2M19 10v4" /></g>,
    camera: <g strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" fill="none" stroke="currentColor"><path d="M2 8l6.553-3.276A1 1 0 019.553 5.618v6.764a1 1 0 01-1.447.894L4 11M9.553 6H19a2 2 0 012 2v8a2 2 0 01-2 2H9.553l-3.276 2.276A1 1 0 015 19v-6.764a1 1 0 01.447-.894L9.553 6z" /><circle cx="14" cy="11" r="2.5" fill="currentColor" /><path d="M5.5 11v.01" /></g>,
    zones: <g strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" fill="none" stroke="currentColor"><path d="M12 2l8 4v8l-8 8-8-8V6l8-4zM6 8l6 4 6-4M8 6l4 2.5M12 2v20" /><circle cx="12" cy="8" r="1.5" fill="currentColor" /></g>,
    bell: <g strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" fill="none" stroke="currentColor"><path d="M12 22c2.21 0 4-1.79 4-4H8c0 2.21 2.79 4 4 4z" /><path d="M18 11V7a6 6 0 00-12 0v4l-2 2v2h16v-2l-2-2z" /></g>,
    anpr: <g strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" fill="none" stroke="currentColor"><rect x="3" y="7" width="18" height="10" rx="1.5" /><path d="M6 11h2M10 11h2M14 11h2M18 11h2M6 14h12" /><rect x="7" y="9" width="2" height="2" rx="0.3" fill="currentColor" /><rect x="13" y="9" width="2" height="2" rx="0.3" fill="currentColor" /></g>,
    reid: <g strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" fill="none" stroke="currentColor"><path d="M5 20c4-4 10-6 14-6" /><circle cx="9" cy="7" r="3" /><circle cx="9" cy="7" r="6" strokeDasharray="1 3" fill="none" /><path d="M15 7l3 3M18 7l-3 3" /></g>,
    case: <g strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" fill="none" stroke="currentColor"><path d="M3 6h18v12a2 2 0 01-2 2H7a2 2 0 01-2-2V6z" /><path d="M8 2h8v4H8zM12 10v8m-4-4h8" /></g>,
    chat: <g strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" fill="none" stroke="currentColor"><path d="M12 2H5a2 2 0 00-2 2v10a2 2 0 002 2h4l5 5V4a2 2 0 012-2h3" /><circle cx="16" cy="8" r="1" fill="currentColor" /><circle cx="19" cy="8" r="1" fill="currentColor" /></g>,
    settings: <g strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" fill="none" stroke="currentColor"><circle cx="12" cy="12" r="3" /><path d="M12 1v6m0 10v6M4.22 4.22l4.24 4.24m7.52 7.52l4.24 4.24M1 12h6m10 0h6M4.22 19.78l4.24-4.24m7.52-7.52l4.24-4.24" /></g>,
  }
  return <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">{icons[name]}</svg>
}

export default function App() {
  const [events, setEvents] = useState<DetectionEvent[]>([])
  const [cameras, setCameras] = useState<Camera[]>([])
  const [zones, setZones] = useState<Zone[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [editingCameraId, setEditingCameraId] = useState<string | null>(null)
  const [connected, setConnected] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [activeTab, setActiveTab] = useState('Dashboard')
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let mounted = true
    let ws: WebSocket | null = null
    let wsTimeoutId: ReturnType<typeof setTimeout> | null = null
    let retryTimeoutId: ReturnType<typeof setTimeout> | null = null
    let retryCount = 0
    const maxRetries = 5
    const wsConnectTimeout = 3000
    const wsUrl = `${API_URL.replace('http', 'ws')}/ws/alerts`

    const connectWebSocket = () => {
      if (!mounted) return
      ws = new WebSocket(wsUrl)
      wsRef.current = ws

      wsTimeoutId = setTimeout(() => {
        if (ws && ws.readyState !== WebSocket.OPEN) {
          console.warn(`WebSocket connection timed out after ${wsConnectTimeout}ms (${wsUrl})`)
          ws.close()
        }
      }, wsConnectTimeout)

      ws.onopen = () => {
        if (wsTimeoutId) clearTimeout(wsTimeoutId)
        retryCount = 0
        console.log('WebSocket connected:', wsUrl)
      }
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          setEvents(prev => [data, ...prev].slice(0, 100))
        } catch { /* ignore malformed messages */ }
      }
      ws.onerror = () => {
        console.warn('WebSocket error:', wsUrl)
      }
      ws.onclose = () => {
        if (wsTimeoutId) clearTimeout(wsTimeoutId)
        if (!mounted) return
        if (retryCount < maxRetries) {
          retryCount++
          const delay = Math.min(1000 * 2 ** retryCount, 10000)
          console.log(`WebSocket reconnecting (attempt ${retryCount}/${maxRetries}) in ${delay}ms`)
          retryTimeoutId = setTimeout(connectWebSocket, delay)
        } else {
          console.warn('WebSocket disconnected after max retries:', wsUrl)
        }
      }
    }

    const fetchInitial = async () => {
      try {
        const [eventsRes, camerasRes, zonesRes] = await Promise.all([
          fetch(`${API_URL}/events?limit=50`),
          fetch(`${API_URL}/cameras`),
          fetch(`${API_URL}/zones`),
        ])
        if (!mounted) return
        if (!eventsRes.ok || !camerasRes.ok) {
          console.warn('REST API error:', { events: eventsRes.status, cameras: camerasRes.status })
          setConnected(false)
          return
        }
        const [eventsData, camerasData, zonesData, alertsData, incidentsData, agentAlertsData, agentIncidentsData] = await Promise.all([
          eventsRes.json(),
          camerasRes.json(),
          zonesRes.ok ? zonesRes.json() : [],
          fetch(`${API_URL}/alerts`).then(r => r.ok ? r.json() : []),
          fetch(`${API_URL}/incidents`).then(r => r.ok ? r.json() : []),
          fetch(`${API_URL}/agent/alerts`).then(r => r.ok ? r.json() : []),
          fetch(`${API_URL}/agent/incidents`).then(r => r.ok ? r.json() : []),
        ])
        setEvents(eventsData)
        setCameras(camerasData)
        if (zonesRes.ok) setZones(zonesData)
        setAlerts([...alertsData, ...agentAlertsData])
        setIncidents([...incidentsData, ...agentIncidentsData])
        setConnected(true)
        connectWebSocket()
      } catch (e) {
        console.error('REST API fetch failed:', e)
        setConnected(false)
      }
    }
    fetchInitial()

    return () => {
      mounted = false
      if (wsTimeoutId) clearTimeout(wsTimeoutId)
      if (retryTimeoutId) clearTimeout(retryTimeoutId)
      if (ws) ws.close()
    }
  }, [])

  const getEventLabel = (e: DetectionEvent) => {
    if (e.plate_text) return `${e.plate_text} (ANPR)`
    if (e.anomaly_label) return `${e.anomaly_label} (Anomaly)`
    if (e.event_type === 'face_match') return `Face Match (Authorized)`
    if (e.event_type === 'reid_match') return `ReID Match`
    return `${e.entity_type} (${e.event_type})`
  }

  const getConfidenceColor = (conf: number) => {
    if (conf >= 0.8) return 'text-green-600'
    if (conf >= 0.6) return 'text-yellow-600'
    return 'text-red-600'
  }

  const getEventBorderColor = (type: string) => {
    switch (type) {
      case 'anpr_read': return 'border-l-blue-500'
      case 'anomaly': return 'border-l-red-500'
      case 'reid_match': return 'border-l-purple-500'
      case 'face_match': return 'border-l-orange-500'
      default: return 'border-l-gray-300'
    }
  }

  const stats = {
    detections: events.filter(e => e.event_type === 'detection').length,
    anpr: events.filter(e => e.event_type === 'anpr_read').length,
    reid: events.filter(e => e.event_type === 'reid_match').length,
    anomalies: events.filter(e => e.event_type === 'anomaly').length,
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans">
      {sidebarOpen && (
        <div className="fixed inset-0 bg-black/40 z-40 lg:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      <aside className={`fixed top-0 left-0 z-50 h-full w-64 bg-white border-r border-slate-200 shadow-sm transform transition-transform duration-200 lg:translate-x-0 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="p-6">
          <div className="flex items-center gap-3 mb-8">
            <img src="/prahari-logo.png" alt="PRAHARI" className="h-8 w-auto object-contain" />
            <div>
              <h1 className="text-lg font-semibold text-slate-900">PRAHARI</h1>
              <p className="text-xs text-slate-500">Control Room</p>
            </div>
          </div>

          <nav className="space-y-1">
            {navItems.map(item => (
              <button
                key={item.label}
                onClick={() => { setActiveTab(item.label); setSidebarOpen(false) }}
                className={`flex items-center gap-3 w-full px-3 py-2 text-sm font-medium rounded-lg transition-all ${activeTab === item.label ? 'bg-blue-50 text-blue-700 shadow-sm' : 'text-slate-600 hover:bg-slate-50'}`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <Icon name={item.icon} />
                </svg>
                {item.label}
              </button>
            ))}
          </nav>
        </div>
      </aside>

      <div className="lg:ml-64 p-6">
        <header className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-slate-900">{activeTab}</h2>
            <p className="text-sm text-slate-500">Live surveillance intelligence</p>
          </div>
          <div className="flex items-center gap-2">
            <span className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium shadow-sm ${connected ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
              <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`}></span>
              {connected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
        </header>

        {activeTab === 'Dashboard' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md transition-shadow">
                <div className="text-xs text-slate-500 mb-1 font-medium">Detections</div>
                <div className="text-2xl font-bold text-slate-900">{stats.detections}</div>
              </div>
              <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md transition-shadow">
                <div className="text-xs text-slate-500 mb-1 font-medium">ANPR Reads</div>
                <div className="text-2xl font-bold text-blue-600">{stats.anpr}</div>
              </div>
              <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md transition-shadow">
                <div className="text-xs text-slate-500 mb-1 font-medium">ReID Matches</div>
                <div className="text-2xl font-bold text-purple-600">{stats.reid}</div>
              </div>
              <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md transition-shadow">
                <div className="text-xs text-slate-500 mb-1 font-medium">Anomalies</div>
                <div className="text-2xl font-bold text-red-600">{stats.anomalies}</div>
              </div>
            </div>

            <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/50">
                <h3 className="text-sm font-semibold text-slate-900">Live Event Feed</h3>
              </div>
              <div className="divide-y divide-slate-100">
                {events.slice(0, 20).map(event => (
                  <div key={event.event_id} className={`px-6 py-3 hover:bg-slate-50 transition-colors border-l-4 ${getEventBorderColor(event.event_type)}`}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-slate-500 font-medium">{event.camera_id}</span>
                        <span className="text-sm text-slate-900">{getEventLabel(event)}</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className={`text-xs font-medium ${getConfidenceColor(event.confidence)}`}>
                          {Math.round(event.confidence * 100)}%
                        </span>
                        <span className="text-xs text-slate-400">
                          {new Date(event.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'Zones' && (
          <div className="space-y-6">
            {editingCameraId ? (
              <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-slate-900">Zone Editor — Camera {editingCameraId}</h3>
                  <button
                    onClick={() => setEditingCameraId(null)}
                    className="px-3 py-2 text-xs text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors"
                  >
                    ← Back to Zones
                  </button>
                </div>
                <ZoneEditor
                  cameraId={editingCameraId}
                  zones={zones.filter(z => z.camera_id === editingCameraId)}
                  onSave={(updatedZones) => {
                    setZones(prev => {
                      const filtered = prev.filter(z => z.camera_id !== editingCameraId)
                      return [...filtered, ...updatedZones]
                    })
                    setEditingCameraId(null)
                  }}
                  onCancel={() => setEditingCameraId(null)}
                />
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <h2 className="text-2xl font-bold text-slate-900">Zones</h2>
                </div>
                <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
                  <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/50">
                    <h3 className="text-sm font-semibold text-slate-900">Camera Zones</h3>
                    <p className="text-xs text-slate-500 mt-1">Intrusion zones, counting lines, and restricted areas</p>
                  </div>
                  <div className="divide-y divide-slate-100">
                    {zones.length === 0 && (
                      <div className="px-6 py-8 text-center text-sm text-slate-500">No zones configured</div>
                    )}
                    {cameras.map(camera => (
                      <div key={camera.camera_id} className="px-6 py-4 hover:bg-slate-50 transition-colors">
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="text-sm font-medium text-slate-900">{camera.camera_id}</div>
                            <div className="text-xs text-slate-500 mt-1">
                              Zone editor: draw intrusion zones, counting lines, no-parking areas
                            </div>
                          </div>
                          <button
                            onClick={() => setEditingCameraId(camera.camera_id)}
                            className="px-3 py-2 text-xs text-blue-700 hover:text-blue-800 hover:bg-blue-50 rounded-lg transition-colors border border-blue-200"
                          >
                            Edit Zones
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {activeTab === 'Cameras' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-2xl font-bold text-slate-900">Cameras</h2>
            </div>

            <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/50">
                <h3 className="text-sm font-semibold text-slate-900">Live Camera Grid</h3>
              </div>
              <div className="p-6">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  {cameras.map(camera => (
                    <div key={camera.camera_id} className="relative bg-slate-900 rounded-lg overflow-hidden shadow-lg group">
                      <img
                        src={`${API_URL}/stream/test_feed/${camera.camera_id}`}
                        alt={camera.camera_id}
                        className="w-full h-48 object-cover"
                        onError={(e) => {
                          (e.target as HTMLImageElement).src = `https://placehold.co/320x192/1e293b/ffffff?text=${camera.camera_id}`
                        }}
                      />
                      <img
                        src={`${API_URL}/stream/mjpeg/${camera.camera_id}?fps=3`}
                        alt={`Live ${camera.camera_id}`}
                        className="absolute inset-0 w-full h-48 object-cover opacity-0 group-hover:opacity-100 transition-opacity"
                      />
                      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-3">
                        <div className="text-white text-sm font-medium">{camera.camera_id}</div>
                        <div className="text-slate-300 text-xs">{camera.event_type || 'online'}</div>
                      </div>
                      <div className="absolute top-2 right-2">
                        <span className="w-2 h-2 bg-green-400 rounded-full shadow-lg animate-pulse"></span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/50">
                <h3 className="text-sm font-semibold text-slate-900">Registered Cameras</h3>
              </div>
              <div className="divide-y divide-slate-100">
                {cameras.map(camera => (
                  <div key={camera.camera_id} className="px-6 py-4 hover:bg-slate-50 transition-colors">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-sm font-medium text-slate-900">{camera.camera_id}</div>
                        <div className="text-xs text-slate-500 mt-1">
                          Last seen: {new Date(camera.last_seen).toLocaleString()}
                        </div>
                      </div>
                      <span className="px-2 py-1 rounded-full text-xs bg-blue-50 text-blue-700 border border-blue-200 font-medium">
                        {camera.event_type}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'Alerts' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-2xl font-bold text-slate-900">Alerts</h2>
              <div className="flex gap-2">
                {['critical', 'high', 'medium', 'low'].map(sev => {
                  const count = alerts.filter(a => a.severity === sev).length
                  const colors: Record<string, string> = {
                    critical: 'bg-red-100 text-red-800 border-red-300',
                    high: 'bg-orange-100 text-orange-800 border-orange-300',
                    medium: 'bg-yellow-100 text-yellow-800 border-yellow-300',
                    low: 'bg-blue-100 text-blue-800 border-blue-300',
                  }
                  return (
                    <span key={sev} className={`px-2 py-1 rounded-lg text-xs font-medium border ${colors[sev]}`}>
                      {sev}: {count}
                    </span>
                  )
                })}
              </div>
            </div>
            <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/50">
                <h3 className="text-sm font-semibold text-slate-900">Active Alerts</h3>
              </div>
              <div className="divide-y divide-slate-100">
                {alerts.slice(0, 10).map(alert => {
                  const sevColors: Record<string, string> = {
                    critical: 'text-red-600 bg-red-50 border-red-200',
                    high: 'text-orange-600 bg-orange-50 border-orange-200',
                    medium: 'text-yellow-600 bg-yellow-50 border-yellow-200',
                    low: 'text-blue-600 bg-blue-50 border-blue-200',
                  }
                  return (
                    <div key={alert.id} className="px-6 py-4 hover:bg-slate-50 transition-colors border-l-4 border-l-gray-300">
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-sm font-medium text-slate-900">{getEventLabel({event_id: alert.event_id, camera_id: alert.camera_id, timestamp: alert.created_at, event_type: alert.alert_type as any, entity_type: 'object' as const, bbox: {x:0,y:0,w:0,h:0}, confidence: alert.confidence, track_id: '', source_repo: '', requires_authorization: false})}</div>
                          <div className="text-xs text-slate-500 mt-1">{alert.camera_id} • {new Date(alert.created_at).toLocaleString()}</div>
                        </div>
                        <span className={`px-2 py-1 rounded-full text-xs font-medium border ${sevColors[alert.severity] || sevColors.medium}`}>
                          {alert.severity?.toUpperCase()}
                        </span>
                      </div>
                    </div>
                  )
                })}
                {alerts.length === 0 && (
                  <div className="px-6 py-8 text-center text-sm text-slate-500">No alerts</div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'Incidents' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-2xl font-bold text-slate-900">Incident Management</h2>
              <div className="flex gap-2">
                {['critical', 'high', 'medium', 'low'].map(sev => {
                  const count = incidents.filter(i => i.severity === sev).length
                  const colors: Record<string, string> = {
                    critical: 'bg-red-100 text-red-800 border-red-300',
                    high: 'bg-orange-100 text-orange-800 border-orange-300',
                    medium: 'bg-yellow-100 text-yellow-800 border-yellow-300',
                    low: 'bg-blue-100 text-blue-800 border-blue-300',
                  }
                  return (
                    <span key={sev} className={`px-2 py-1 rounded-lg text-xs font-medium border ${colors[sev]}`}>
                      {sev}: {count}
                    </span>
                  )
                })}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                {['open', 'acknowledged', 'investigating', 'resolved', 'dismissed'].map(st => {
                const count = incidents.filter(i => i.status === st).length
                const bgColors: Record<string, string> = {
                  open: 'bg-red-50 border-red-200 text-red-700',
                  acknowledged: 'bg-orange-50 border-orange-200 text-orange-700',
                  investigating: 'bg-blue-50 border-blue-200 text-blue-700',
                  resolved: 'bg-green-50 border-green-200 text-green-700',
                  dismissed: 'bg-slate-50 border-slate-200 text-slate-500',
                }
                return (
                  <div key={st} className={`border rounded-xl p-4 ${bgColors[st] || bgColors.open}`}>
                    <div className="text-xs font-medium mb-1 capitalize">{st}</div>
                    <div className="text-2xl font-bold">{count}</div>
                  </div>
                )
              })}
            </div>

            <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/50">
                <h3 className="text-sm font-semibold text-slate-900">Active Incidents</h3>
              </div>
              <div className="divide-y divide-slate-100">
                {incidents.map(incident => (
                  <div key={incident.id} className="px-6 py-4 hover:bg-slate-50 transition-colors">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className={`px-2 py-1 rounded-full text-xs font-semibold border ${
                            incident.severity === 'critical' ? 'bg-red-100 text-red-800 border-red-300' :
                            incident.severity === 'high' ? 'bg-orange-100 text-orange-800 border-orange-300' :
                            incident.severity === 'medium' ? 'bg-yellow-100 text-yellow-800 border-yellow-300' :
                            'bg-blue-100 text-blue-800 border-blue-300'
                          }`}>
                            {incident.severity?.toUpperCase()}
                          </span>
                          <span className={`px-2 py-1 rounded-full text-xs font-medium border ${
                            incident.status === 'open' ? 'bg-red-50 text-red-700 border-red-200' :
                            incident.status === 'acknowledged' ? 'bg-orange-50 text-orange-700 border-orange-200' :
                            incident.status === 'investigating' ? 'bg-blue-50 text-blue-700 border-blue-200' :
                            incident.status === 'resolved' ? 'bg-green-50 text-green-700 border-green-200' :
                            'bg-slate-50 text-slate-600 border-slate-300'
                          }`}>
                            {incident.status}
                          </span>
                        </div>
                        <div className="text-sm font-medium text-slate-900 mt-2">{incident.title}</div>
                        <div className="text-xs text-slate-500 mt-1">
                          Camera: {incident.camera_id} • Created: {new Date(incident.created_at).toLocaleString()}
                        </div>
                        {incident.description && (
                          <div className="text-xs text-slate-600 mt-1">{incident.description}</div>
                        )}
                      </div>
                      {incident.assigned_to && (
                        <span className="text-xs text-slate-500">Assigned: {incident.assigned_to}</span>
                      )}
                    </div>
                  </div>
                ))}
                {incidents.length === 0 && (
                  <div className="px-6 py-8 text-center text-sm text-slate-500">No incidents</div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'ANPR' && (
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/50">
              <h3 className="text-sm font-semibold text-slate-900">License Plate Recognition</h3>
            </div>
            <div className="divide-y divide-slate-100">
              {events.filter(e => e.event_type === 'anpr_read').slice(0, 20).map(event => (
                <div key={event.event_id} className="px-6 py-3 hover:bg-slate-50 transition-colors">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-mono text-blue-700 font-medium">{event.plate_text}</span>
                      <span className="text-xs text-slate-500">{event.camera_id}</span>
                    </div>
                    <span className="text-xs text-slate-400">
                      {new Date(event.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'ReID' && (
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/50">
              <h3 className="text-sm font-semibold text-slate-900">Cross-Camera ReID Matches</h3>
            </div>
            <div className="divide-y divide-slate-100">
              {events.filter(e => e.event_type === 'reid_match').slice(0, 20).map(event => (
                <div key={event.event_id} className="px-6 py-3 hover:bg-slate-50 transition-colors">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-slate-500 font-medium">{event.camera_id}</span>
                      <span className="text-sm text-purple-700 font-medium">Match found</span>
                    </div>
                    <span className="text-xs text-slate-400">
                      {new Date(event.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'Case Files' && (
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-6">
            <h3 className="text-sm font-semibold text-slate-900 mb-4">Case File Export</h3>
            <p className="text-sm text-slate-600">Case file export module ready. Events are timestamped and can be exported with SHA-256 hash for court admissibility.</p>
          </div>
        )}

        {activeTab === 'AI Chat' && (
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-6">
            <h3 className="text-sm font-semibold text-slate-900 mb-4">PRAHARI AI Assistant</h3>
            <p className="text-sm text-slate-600 mb-4">Ask questions about cameras, alerts, events, people, vehicles, and license plates.</p>
            <div className="space-y-3">
              <div className="bg-slate-50 rounded-lg p-3 text-sm text-slate-700">
                <strong>Try asking:</strong>
                <ul className="list-disc list-inside mt-2 space-y-1 text-xs">
                  <li>"How many cameras are online?"</li>
                  <li>"Show me recent alerts"</li>
                  <li>"How many incidents are critical?"</li>
                  <li>"How many people were detected?"</li>
                  <li>"What vehicles were seen?"</li>
                  <li>"Show me recent license plates"</li>
                  <li>"What is the alert severity level?"</li>
                </ul>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'Settings' && (
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-6">
            <h3 className="text-sm font-semibold text-slate-900 mb-4">System Settings</h3>
            <div className="space-y-4">
              <div>
                <label className="text-xs text-slate-500 block mb-2 font-medium">Fusion API URL</label>
                <input type="text" value={API_URL} readOnly className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700" />
              </div>
              <div>
                <label className="text-xs text-slate-500 block mb-2 font-medium">WebSocket Status</label>
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`}></span>
                  <span className="text-sm text-slate-700">{connected ? 'Connected' : 'Disconnected'}</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
