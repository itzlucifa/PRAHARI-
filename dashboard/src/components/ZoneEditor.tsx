import { useState, useRef, useEffect } from 'react'
import { Zone } from '../types'

interface ZoneEditorProps {
  cameraId: string
  zones: Zone[]
  onSave: (zones: Zone[]) => void
  onCancel: () => void
}

const ZONE_COLORS: Record<string, string> = {
  intrusion: '#EF4444',
  counting: '#3B82F6',
  no_parking: '#F59E0B',
}

const ZONE_LABELS: Record<string, string> = {
  intrusion: 'Intrusion',
  counting: 'Counting Line',
  no_parking: 'No Parking',
}

export default function ZoneEditor({ cameraId, zones: initialZones, onSave, onCancel }: ZoneEditorProps) {
  const [zones, setZones] = useState<Zone[]>(initialZones)
  const [drawing, setDrawing] = useState(false)
  const [currentPoints, setCurrentPoints] = useState<{ x: number; y: number }[]>([])
  const [zoneType, setZoneType] = useState<'intrusion' | 'counting' | 'no_parking'>('intrusion')
  const [zoneName, setZoneName] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [mode, setMode] = useState<'draw' | 'select'>('select')
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const imgRef = useRef<HTMLImageElement>(new Image())

  const drawZone = (ctx: CanvasRenderingContext2D, zone: Zone) => {
    if (zone.points.length < 2) return

    const color = ZONE_COLORS[zone.type] || '#6B7280'

    ctx.strokeStyle = color
    ctx.fillStyle = color + '20'
    ctx.lineWidth = 2

    ctx.beginPath()
    zone.points.forEach((pt: number[], i: number) => {
      const [x, y] = pt
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.closePath()
    ctx.fill()
    ctx.stroke()

    if (zone.points.length > 0) {
      const [cx, cy] = zone.points[0]
      ctx.fillStyle = color
      ctx.font = '12px sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText(zone.name || `Zone ${zone.zone_id.substring(0, 4)}`, cx, cy - 8)
    }
  }

  const drawCurrent = (ctx: CanvasRenderingContext2D) => {
    if (currentPoints.length < 2) return

    const color = ZONE_COLORS[zoneType]
    ctx.strokeStyle = color
    ctx.fillStyle = color + '20'
    ctx.lineWidth = 2
    ctx.setLineDash([4, 4])

    ctx.beginPath()
    currentPoints.forEach((pt, i) => {
      if (i === 0) ctx.moveTo(pt.x, pt.y)
      else ctx.lineTo(pt.x, pt.y)
    })
    ctx.closePath()
    ctx.fill()
    ctx.stroke()

    ctx.setLineDash([])
  }

  const redraw = () => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    canvas.width = canvas.offsetWidth
    canvas.height = canvas.offsetHeight

    ctx.clearRect(0, 0, canvas.width, canvas.height)

    ctx.drawImage(imgRef.current, 0, 0, canvas.width, canvas.height)

    zones.forEach(z => drawZone(ctx, z))
    drawCurrent(ctx)
  }

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (mode !== 'draw' || !drawing) return

    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top

    setCurrentPoints(prev => [...prev, { x, y }])
  }

  const handleFinishZone = () => {
    if (currentPoints.length < 3) {
      alert('Zone must have at least 3 points')
      return
    }

    const newZone: Zone = {
      camera_id: cameraId,
      zone_id: editingId || `zone_${Date.now()}`,
      name: zoneName || `Zone ${zones.length + 1}`,
      type: zoneType,
      points: currentPoints.map(p => [p.x, p.y]),
    }

    if (editingId) {
      setZones(prev => prev.map(z => z.zone_id === editingId ? newZone : z))
      setEditingId(null)
    } else {
      setZones(prev => [...prev, newZone])
    }

    setCurrentPoints([])
    setDrawing(false)
    setZoneName('')
    setMode('select')
  }

  const handleDeleteZone = (zoneId: string) => {
    setZones(prev => prev.filter(z => z.zone_id !== zoneId))
  }

  const handleEditZone = (zone: Zone) => {
    setEditingId(zone.zone_id)
    setZoneType(zone.type as 'intrusion' | 'counting' | 'no_parking')
    setZoneName(zone.name)
      setCurrentPoints(zone.points.map(([x, y]: number[]) => ({ x, y })))
    setMode('draw')
    setDrawing(true)
  }

  const handleSave = () => {
    onSave(zones)
  }

  useEffect(() => {
    imgRef.current.onload = redraw
  }, [])

  useEffect(() => {
    redraw()
  }, [zones, currentPoints, zoneType, drawing])

  const sampleStream = 'https://placehold.co/640x480/1e293b/ffffff?text=Camera+' + cameraId

  return (
    <div className="space-y-4">
      <input type="hidden" name="csrf-token" />
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <select
            value={zoneType}
            onChange={e => setZoneType(e.target.value as 'intrusion' | 'counting' | 'no_parking')}
            className="px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white"
          >
            <option value="intrusion">Intrusion Zone</option>
            <option value="counting">Counting Line</option>
            <option value="no_parking">No Parking Zone</option>
          </select>

          <input
            type="text"
            placeholder="Zone name"
            value={zoneName}
            onChange={e => setZoneName(e.target.value)}
            className="px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white w-48"
          />
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setMode('select')}
            className={`px-3 py-2 text-xs font-medium rounded-lg transition-all ${mode === 'select' ? 'bg-blue-100 text-blue-700 border border-blue-200' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
          >
            Select
          </button>
          <button
            onClick={() => { setMode('draw'); setDrawing(false); setCurrentPoints([]); setEditingId(null); setZoneName('') }}
            className={`px-3 py-2 text-xs font-medium rounded-lg transition-all ${mode === 'draw' ? 'bg-blue-100 text-blue-700 border border-blue-200' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
          >
            Draw New
          </button>
          <button
            onClick={handleSave}
            className="px-4 py-2 bg-blue-600 text-white text-xs font-medium rounded-lg hover:bg-blue-700 transition-colors"
          >
            Save Zones
          </button>
          <button
            onClick={onCancel}
            className="px-4 py-2 bg-slate-100 text-slate-700 text-xs font-medium rounded-lg hover:bg-slate-200 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>

      <div className="flex items-center gap-4 text-xs text-slate-500">
        <span>Zone color: <strong style={{ color: ZONE_COLORS[zoneType] }}>{ZONE_LABELS[zoneType]}</strong></span>
        <span>Click points on the canvas to draw a polygon. Right-click or press Esc to cancel drawing.</span>
      </div>

      <div className="relative inline-block bg-slate-900 rounded-lg overflow-hidden">
        <img
          ref={imgRef}
          src={sampleStream}
          alt={`Camera ${cameraId}`}
          className="object-contain"
          onLoad={redraw}
          style={{ maxWidth: '100%', maxHeight: '480px' }}
        />
        <canvas
          ref={canvasRef}
          onMouseDown={handleMouseDown}
          className="absolute top-0 left-0"
          style={{ width: '100%', height: '100%' }}
        />
      </div>

      {mode === 'draw' && currentPoints.length > 0 && (
        <div className="flex gap-2">
          <button
            onClick={handleFinishZone}
            className="px-4 py-2 bg-green-600 text-white text-xs font-medium rounded-lg hover:bg-green-700 transition-colors"
          >
            {editingId ? 'Update Zone' : 'Finish Zone'}
          </button>
          <button
            onClick={() => { setCurrentPoints([]); setDrawing(false); setMode('select') }}
            className="px-4 py-2 bg-slate-100 text-slate-700 text-xs font-medium rounded-lg hover:bg-slate-200 transition-colors"
          >
            Cancel Drawing
          </button>
        </div>
      )}

      {zones.map(zone => (
        <div
          key={zone.zone_id}
          className="flex items-center justify-between p-3 bg-slate-50 rounded-lg border border-slate-200"
        >
          <div className="flex items-center gap-3">
            <span
              className="w-3 h-3 rounded-full"
              style={{ backgroundColor: ZONE_COLORS[zone.type] || '#6B7280' }}
            />
            <div>
              <div className="text-sm font-medium text-slate-900">{zone.name}</div>
              <div className="text-xs text-slate-500">
                {zone.type} | {zone.points.length} points
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => handleEditZone(zone)}
              className="px-2 py-1 text-xs text-slate-600 hover:text-slate-900 hover:bg-slate-200 rounded"
            >
              Edit
            </button>
            <button
              onClick={() => handleDeleteZone(zone.zone_id)}
              className="px-2 py-1 text-xs text-red-600 hover:text-red-700 hover:bg-red-50 rounded"
            >
              Delete
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
