import { useEffect, useState, useRef } from 'react'
import ZoneEditor from './components/ZoneEditor'
import { DetectionEvent, Camera, Zone } from './types'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const navItems = [
  { label: 'Dashboard', icon: 'grid' },
  { label: 'Cameras', icon: 'camera' },
  { label: 'Zones', icon: 'map' },
  { label: 'Alerts', icon: 'bell' },
  { label: 'ANPR', icon: 'file-text' },
  { label: 'ReID', icon: 'users' },
  { label: 'Case Files', icon: 'folder' },
  { label: 'AI Chat', icon: 'chat' },
  { label: 'Settings', icon: 'settings' },
]

function Icon({ name, className }: { name: string; className?: string }) {
  const icons: Record<string, JSX.Element> = {
    grid: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />,
    camera: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />,
    bell: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />,
    'file-text': <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />,
    users: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />,
    folder: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />,
    map: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />,
    chat: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />,
    settings: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37.996.608 2.296.07 2.572-1.065z" />,
  }
  return <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">{icons[name]}</svg>
}

export default function App() {
  const [events, setEvents] = useState<DetectionEvent[]>([])
  const [cameras, setCameras] = useState<Camera[]>([])
  const [zones, setZones] = useState<Zone[]>([])
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
        const [eventsData, camerasData, zonesData] = await Promise.all([
          eventsRes.json(),
          camerasRes.json(),
          zonesRes.ok ? zonesRes.json() : [],
        ])
        setEvents(eventsData)
        setCameras(camerasData)
        if (zonesRes.ok) setZones(zonesData)
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
        )}

        {activeTab === 'Alerts' && (
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/50">
              <h3 className="text-sm font-semibold text-slate-900">Active Alerts</h3>
            </div>
            <div className="divide-y divide-slate-100">
              {events.filter(e => e.confidence > 0.8).slice(0, 10).map(event => (
                <div key={event.event_id} className="px-6 py-4 hover:bg-red-50 transition-colors">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm font-medium text-slate-900">{getEventLabel(event)}</div>
                      <div className="text-xs text-slate-500 mt-1">{event.camera_id}</div>
                    </div>
                    <span className="text-xs font-medium text-red-700 bg-red-50 px-2 py-1 rounded-full border border-red-200">
                      High Confidence
                    </span>
                  </div>
                </div>
              ))}
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
                  <li>"How many people were detected?"</li>
                  <li>"What vehicles were seen?"</li>
                  <li>"Show me recent license plates"</li>
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
