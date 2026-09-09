export interface DetectionEvent {
  event_id: string
  camera_id: string
  timestamp: string
  event_type: 'detection' | 'anomaly' | 'anpr_read' | 'reid_match' | 'face_match'
  entity_type: 'person' | 'vehicle' | 'object'
  bbox: { x: number; y: number; w: number; h: number }
  confidence: number
  track_id: string
  embedding_id?: string
  plate_text?: string
  anomaly_label?: string
  source_repo: string
  requires_authorization: boolean
}

export interface Camera {
  camera_id: string
  last_seen: string
  event_type: string
}

export interface Zone {
  camera_id: string
  zone_id: string
  name: string
  type: string
  points: number[][]
}
