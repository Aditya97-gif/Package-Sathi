"""
main.py — FastAPI backend for the Legal Metrology Compliance Checker.

Endpoints:
  POST /api/scan          — Upload label image, run full pipeline, return compliance report
  GET  /api/history       — List past scans (paginated)
  GET  /api/scan/{id}     — Get full details of a specific scan
  GET  /api/report/{id}   — Download PDF compliance report for a scan
  GET  /api/dashboard     — Aggregated stats for the dashboard
  GET  /api/health        — Health check
"""
from __future__ import annotations

import logging
import os
import shutil
import uuid
from datetime import datetime
from typing import List, Optional

import cv2
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

# Internal modules
from database import Scan, Violation, get_db, init_db
from OCR import run_multipass_tesseract, run_easyocr, EASYOCR_AVAILABLE
from nlp import extract_fields
from rule_engine import run_compliance_checks
from report_generator import generate_pdf_report
from font_size_checker import check_font_sizes

# ---------------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Directory Setup
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "..", "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Legal Metrology Compliance Checker",
    description=(
        "Automated compliance checker for the Legal Metrology (Packaged Commodities) Rules, 2011. "
        "Upload a label image to extract mandatory declarations and verify compliance."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow the React dev server (localhost:5173) and production origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("Database initialised.")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["System"])
def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "easyocr_available": EASYOCR_AVAILABLE,
    }


@app.post("/api/scan", tags=["Scanning"], summary="Upload a label image and run compliance check")
async def scan_label(
    file: UploadFile = File(..., description="Label image (JPEG, PNG, WebP)"),
    engine: str = Form("tesseract", description="OCR engine: 'tesseract' or 'easyocr'"),
    use_llm: bool = Form(True, description="Use Ollama mistral:7b as LLM fallback for field extraction"),
    db: Session = Depends(get_db),
):
    # ── 1. Validate & save uploaded file ───────────────────────────────────
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/jpg"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}. Use JPEG, PNG, or WebP.")

    ext = os.path.splitext(file.filename)[-1].lower() or ".jpg"
    unique_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(UPLOAD_DIR, unique_name)

    with open(save_path, "wb") as out_file:
        shutil.copyfileobj(file.file, out_file)

    logger.info("Saved uploaded image: %s", save_path)

    # ── 2. Run OCR ──────────────────────────────────────────────────────────
    img = cv2.imread(save_path)
    if img is None:
        raise HTTPException(status_code=422, detail="Could not decode the uploaded image. Ensure it is a valid image file.")

    try:
        if engine == "easyocr" and EASYOCR_AVAILABLE:
            ocr_text = run_easyocr(save_path)
            engine_used = "easyocr"
        else:
            ocr_text = run_multipass_tesseract(img)
            engine_used = "tesseract"
    except Exception as exc:
        logger.exception("OCR failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {exc}")

    logger.info("OCR complete. Extracted %d characters.", len(ocr_text))

    # ── 3. Extract fields (NLP pipeline) ───────────────────────────────────
    try:
        extracted_fields, llm_used = extract_fields(ocr_text, use_llm=use_llm)
    except Exception as exc:
        logger.exception("Field extraction failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Field extraction failed: {exc}")

    # ── 3b. Phase 4: Font-size / readability analysis ───────────────────────
    font_report = None
    try:
        font_report = check_font_sizes(img, image_path=save_path)
        logger.info(
            "Font-size check: %d blocks, %d failing, DPI=%.0f",
            font_report.total_blocks_checked,
            font_report.failing_blocks,
            font_report.dpi_used,
        )
    except Exception as exc:
        logger.warning("Font-size check failed (non-fatal): %s", exc)

    # ── 4. Run compliance checks ────────────────────────────────────────────
    compliance = run_compliance_checks(extracted_fields)
    compliance_dict = compliance.to_dict()

    # ── 5. Persist to database ──────────────────────────────────────────────
    scan = Scan(
        image_filename=file.filename,
        image_path=save_path,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        overall_status=compliance.overall_status,
        compliance_score=compliance.compliance_score,
        engine_used=engine_used,
        llm_used=llm_used,
    )
    db.add(scan)
    db.flush()  # get the ID before generating the report

    # Persist violations
    for v in compliance.violations:
        db.add(Violation(
            scan_id=scan.id,
            field_id=v.field_id,
            field_label=v.field_label,
            severity=v.severity,
            message=v.message,
            rule_ref=v.rule_ref,
        ))

    # ── 6. Generate PDF report ──────────────────────────────────────────────
    try:
        report_path = generate_pdf_report(
            scan_id=scan.id,
            image_filename=file.filename,
            extracted_fields=extracted_fields,
            compliance_report=compliance_dict,
            ocr_text=ocr_text,
        )
        scan.report_path = report_path
    except Exception as exc:
        logger.warning("PDF generation failed (non-fatal): %s", exc)
        report_path = None

    db.commit()
    db.refresh(scan)

    # ── 7. Return response ──────────────────────────────────────────────────
    return JSONResponse(content={
        "scan_id": scan.id,
        "image_filename": file.filename,
        "engine_used": engine_used,
        "llm_used": llm_used,
        "ocr_text": ocr_text,
        "extracted_fields": extracted_fields,
        "compliance_report": compliance_dict,
        "font_size_report": font_report.to_dict() if font_report else None,
        "report_available": report_path is not None,
    })


@app.get("/api/history", tags=["History"], summary="List past scans")
def get_history(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    scans = (
        db.query(Scan)
        .order_by(Scan.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    total = db.query(Scan).count()
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "scans": [
            {
                "id": s.id,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "image_filename": s.image_filename,
                "overall_status": s.overall_status,
                "compliance_score": s.compliance_score,
                "engine_used": s.engine_used,
                "llm_used": s.llm_used,
                "violation_count": len(s.violations),
            }
            for s in scans
        ],
    }


@app.get("/api/scan/{scan_id}", tags=["Scanning"], summary="Get full scan details")
def get_scan(scan_id: int, db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail=f"Scan #{scan_id} not found.")
    return scan.to_dict()


@app.get("/api/report/{scan_id}", tags=["Reports"], summary="Download PDF compliance report")
def download_report(scan_id: int, db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail=f"Scan #{scan_id} not found.")
    if not scan.report_path or not os.path.exists(scan.report_path):
        # Try to regenerate on the fly
        try:
            compliance_dict = {
                "overall_status": scan.overall_status,
                "compliance_score": scan.compliance_score,
                "checks": [v.to_dict() for v in scan.violations],
                "violations": [v.to_dict() for v in scan.violations],
            }
            path = generate_pdf_report(
                scan_id=scan.id,
                image_filename=scan.image_filename,
                extracted_fields=scan.extracted_fields or {},
                compliance_report=compliance_dict,
                ocr_text=scan.ocr_text or "",
            )
            scan.report_path = path
            db.commit()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Could not generate report: {exc}")
    return FileResponse(
        path=scan.report_path,
        media_type="application/pdf",
        filename=f"compliance_report_scan_{scan_id}.pdf",
    )


@app.get("/api/dashboard", tags=["Dashboard"], summary="Aggregated stats for the dashboard")
def get_dashboard_stats(db: Session = Depends(get_db)):
    """Return aggregated statistics for the dashboard: totals, score distribution, recent scans."""
    from sqlalchemy import func

    total_scans = db.query(Scan).count()
    compliant_count = db.query(Scan).filter(Scan.overall_status == "compliant").count()
    non_compliant_count = db.query(Scan).filter(Scan.overall_status == "non_compliant").count()

    # Average compliance score
    avg_score_result = db.query(func.avg(Scan.compliance_score)).scalar()
    avg_score = round(avg_score_result or 0.0, 1)

    # Engine usage breakdown
    engine_counts = (
        db.query(Scan.engine_used, func.count(Scan.id))
        .group_by(Scan.engine_used)
        .all()
    )

    # Violation field frequency — top 10
    violation_counts = (
        db.query(Violation.field_label, func.count(Violation.id))
        .group_by(Violation.field_label)
        .order_by(func.count(Violation.id).desc())
        .limit(10)
        .all()
    )

    # Recent 30 scans for trend chart (chronological order)
    recent_scans = (
        db.query(Scan.id, Scan.created_at, Scan.overall_status, Scan.compliance_score)
        .order_by(Scan.created_at.desc())
        .limit(30)
        .all()
    )

    return {
        "total_scans": total_scans,
        "compliant_count": compliant_count,
        "non_compliant_count": non_compliant_count,
        "avg_compliance_score": avg_score,
        "engine_breakdown": [{"engine": e, "count": c} for e, c in engine_counts],
        "top_violations": [{"field": f, "count": c} for f, c in violation_counts],
        "recent_scans": [
            {
                "id": s.id,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "status": s.overall_status,
                "score": round(s.compliance_score or 0, 1),
            }
            for s in reversed(recent_scans)
        ],
    }
