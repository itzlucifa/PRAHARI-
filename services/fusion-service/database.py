from sqlalchemy import create_engine, Column, String, Float, Integer, Text, Boolean, BigInteger, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
import logging

logger = logging.getLogger("fusion")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://prahari:prahari@postgres:5432/prahari"
)

try:
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    DB_AVAILABLE = True
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        logger.warning("PostgreSQL not available, falling back to in-memory")
        DB_AVAILABLE = False
except Exception as exc:
    logger.warning("Database engine init failed: %s", exc)
    DB_AVAILABLE = False
    SessionLocal = None
    Base = None


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    rtsp_url = Column(String, nullable=True)
    status = Column(String, default="online")
    last_seen = Column(String, nullable=True)
    created_at = Column(String, nullable=True)


class Event(Base):
    __tablename__ = "events"

    id = Column(String, primary_key=True)
    camera_id = Column(String, index=True, nullable=False)
    timestamp = Column(String, index=True, nullable=False)
    event_type = Column(String, index=True, nullable=False)
    entity_type = Column(String, nullable=True)
    bbox = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    track_id = Column(String, index=True, nullable=True)
    embedding_id = Column(String, nullable=True)
    plate_text = Column(String, nullable=True)
    anomaly_label = Column(String, nullable=True)
    source_repo = Column(String, nullable=True)
    requires_authorization = Column(Boolean, default=False)
    received_at = Column(BigInteger, index=True)

    __table_args__ = (
        Index("idx_events_camera_timestamp", "camera_id", "timestamp"),
        Index("idx_events_type_timestamp", "event_type", "timestamp"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String, primary_key=True)
    event_id = Column(String, ForeignKey("events.id"), nullable=False)
    camera_id = Column(String, index=True, nullable=False)
    alert_type = Column(String, index=True, nullable=False)
    confidence = Column(Float, nullable=True)
    status = Column(String, default="open")
    created_at = Column(String, index=True, nullable=False)
    acknowledged_by = Column(String, nullable=True)
    notes = Column(Text, nullable=True)


def init_db():
    if not DB_AVAILABLE:
        return
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        logger.warning("Database init failed: %s", exc)