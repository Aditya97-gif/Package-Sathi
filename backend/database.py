"""
database.py — SQLAlchemy models and DB session setup for the
Legal Metrology Compliance Checker backend.

Tables:
  scans      — one row per uploaded label image / compliance check
  violations — one row per failing / warning check result per scan
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Generator

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

# ---------------------------------------------------------------------------
# Database URL — SQLite file next to the data/ directory
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "..", "data", "compliance.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

DATABASE_URL = f"sqlite:///{os.path.abspath(DB_PATH)}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # required for SQLite + FastAPI
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Scan(Base):
    """
    One record per label scan.  The extracted fields and compliance metadata
    are stored as JSON-encoded text columns for simplicity.
    """
    __tablename__ = "scans"

    id                = Column(Integer, primary_key=True, index=True, autoincrement=True)
    created_at        = Column(DateTime, default=datetime.utcnow, nullable=False)

    # File info
    image_filename    = Column(String(512), nullable=True)
    image_path        = Column(String(1024), nullable=True)

    # OCR + NLP outputs
    ocr_text          = Column(Text, nullable=True)
    _extracted_fields = Column("extracted_fields", Text, nullable=True)

    # Compliance summary
    overall_status    = Column(String(32), nullable=True)   # "compliant" | "non_compliant"
    compliance_score  = Column(Float, nullable=True)

    # Processing metadata
    engine_used       = Column(String(32), nullable=True)   # "tesseract" | "easyocr"
    llm_used          = Column(Boolean, default=False)

    # Path to generated PDF
    report_path       = Column(String(1024), nullable=True)

    # Relationship to violations
    violations = relationship(
        "Violation",
        back_populates="scan",
        cascade="all, delete-orphan",
        lazy="select",
    )

    # ------------------------------------------------------------------
    # Helpers for the JSON-encoded extracted_fields column
    # ------------------------------------------------------------------
    @property
    def extracted_fields(self) -> dict:
        if self._extracted_fields is None:
            return {}
        try:
            return json.loads(self._extracted_fields)
        except (json.JSONDecodeError, TypeError):
            return {}

    @extracted_fields.setter
    def extracted_fields(self, value: dict):
        self._extracted_fields = json.dumps(value) if value is not None else None

    def to_dict(self) -> dict:
        return {
            "id":               self.id,
            "created_at":       self.created_at.isoformat() if self.created_at else None,
            "image_filename":   self.image_filename,
            "ocr_text":         self.ocr_text,
            "extracted_fields": self.extracted_fields,
            "overall_status":   self.overall_status,
            "compliance_score": self.compliance_score,
            "engine_used":      self.engine_used,
            "llm_used":         self.llm_used,
            "report_available": bool(self.report_path),
            "violation_count":  len(self.violations),
            "compliance_report": {
                "overall_status":   self.overall_status,
                "compliance_score": self.compliance_score,
                "checks":           [v.to_dict() for v in self.violations],
                "violations":       [v.to_dict() for v in self.violations],
            },
        }


class Violation(Base):
    """
    One record per compliance check that resulted in a 'fail' or 'warning'.
    Also used to store all check results for detailed history display.
    """
    __tablename__ = "violations"

    id          = Column(Integer, primary_key=True, index=True, autoincrement=True)
    scan_id     = Column(Integer, ForeignKey("scans.id", ondelete="CASCADE"), nullable=False)

    field_id    = Column(String(64),  nullable=True)
    field_label = Column(String(128), nullable=True)
    severity    = Column(String(16),  nullable=True)   # "error" | "warning" | "info"
    message     = Column(Text,        nullable=True)
    rule_ref    = Column(String(64),  nullable=True)

    scan = relationship("Scan", back_populates="violations")

    def to_dict(self) -> dict:
        return {
            "field_id":    self.field_id,
            "field_label": self.field_label,
            "severity":    self.severity,
            "message":     self.message,
            "rule_ref":    self.rule_ref,
            # Provide compatible keys so the frontend check list renders correctly
            "status":      "fail" if self.severity == "error" else "warning",
        }


# ---------------------------------------------------------------------------
# Helpers used by FastAPI
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create all tables (no-op if they already exist)."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
