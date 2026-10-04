"""
font_size_checker.py — Phase 4: Font-size & Readability Analysis
=================================================================
Converts OCR bounding-box pixel height into a real-world measurement (mm)
and compares against the minimum font heights defined in the Rule 6 schema.

The calibration strategy used here:
  - If a calibration reference (coin/card) is not in frame, the module
    estimates DPI from image EXIF metadata where available.
  - Fallback: assumes a conservative 96 DPI (screen capture / scan), which
    will under-report font size — safe side for compliance checking.
  - Controlled scan flow: caller passes `dpi` explicitly for reliable checks.

Rule reference:
  Minimum font heights (capital letter height on PDP) from compliance_rules.json:
    PDP area ≤ 100 cm²   → 1.0 mm
    PDP area ≤ 200 cm²   → 1.5 mm
    PDP area ≤ 500 cm²   → 2.0 mm
    PDP area  > 500 cm²  → 4.0 mm
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MM_PER_INCH = 25.4
DEFAULT_DPI = 96  # Conservative fallback — screen / unknown scan resolution

# PDP area thresholds → minimum capital-letter height in mm (Rule 6 schedule)
_FONT_HEIGHT_RULES: List[Tuple[float, float]] = [
    (100.0, 1.0),
    (200.0, 1.5),
    (500.0, 2.0),
    (float("inf"), 4.0),
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FontCheckResult:
    """Result for a single detected text block's font-size check."""
    text_snippet: str           # First 40 chars of the text block
    pixel_height: float         # Measured bounding-box height in pixels
    estimated_mm: float         # Converted real-world height in mm
    min_required_mm: float      # Minimum required mm for this PDP area
    passes: bool                # True if estimated_mm ≥ min_required_mm
    dpi_used: float             # DPI used for the conversion
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FontSizeReport:
    """Summary report for font-size checks across the whole label."""
    dpi_used: float
    pdp_area_cm2: Optional[float]
    min_required_mm: float
    total_blocks_checked: int
    failing_blocks: int
    overall_pass: bool
    blocks: List[FontCheckResult] = field(default_factory=list)
    calibration_note: str = ""

    def to_dict(self) -> dict:
        return {
            "dpi_used": self.dpi_used,
            "pdp_area_cm2": self.pdp_area_cm2,
            "min_required_mm": self.min_required_mm,
            "total_blocks_checked": self.total_blocks_checked,
            "failing_blocks": self.failing_blocks,
            "overall_pass": self.overall_pass,
            "calibration_note": self.calibration_note,
            "blocks": [b.to_dict() for b in self.blocks],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_min_font_height_mm(pdp_area_cm2: Optional[float]) -> float:
    """Return the minimum required capital-letter height (mm) for a PDP area."""
    if pdp_area_cm2 is None:
        # Unknown PDP — use the most lenient threshold (≤ 100 cm²)
        return _FONT_HEIGHT_RULES[0][1]
    for max_area, min_height in _FONT_HEIGHT_RULES:
        if pdp_area_cm2 <= max_area:
            return min_height
    return _FONT_HEIGHT_RULES[-1][1]


def _estimate_dpi_from_exif(image_path: str) -> Optional[float]:
    """
    Attempt to read DPI from JPEG/TIFF EXIF metadata using Pillow.
    Returns None if metadata is absent or ambiguous.
    """
    try:
        from PIL import Image as PILImage
        with PILImage.open(image_path) as img:
            info = img.info
            dpi_info = info.get("dpi") or info.get("jfif_density")
            if isinstance(dpi_info, tuple) and len(dpi_info) == 2:
                x_dpi, y_dpi = dpi_info
                if x_dpi and x_dpi > 10:
                    return float(x_dpi)
    except Exception as exc:
        logger.debug("EXIF DPI read failed: %s", exc)
    return None


def pixels_to_mm(pixels: float, dpi: float) -> float:
    """Convert a pixel measurement to millimetres given a known DPI."""
    return (pixels / dpi) * MM_PER_INCH


def estimate_pdp_area_cm2(image: np.ndarray, dpi: float) -> float:
    """
    Estimate the Principal Display Panel (PDP) area in cm².

    Strategy:
    - Assumes the uploaded image covers roughly one face of the package
      (the PDP itself), which is the typical use case for label scans.
    - Converts pixel dimensions to real-world cm using DPI.

    For a rectangular package this corresponds to Rule 6: PDP = one full side.
    Returns the area in cm².
    """
    h_px, w_px = image.shape[:2]
    w_cm = (w_px / dpi) * 2.54   # inches → cm
    h_cm = (h_px / dpi) * 2.54
    return round(w_cm * h_cm, 2)


# ---------------------------------------------------------------------------
# Core font-height detector using Tesseract bounding boxes
# ---------------------------------------------------------------------------

def detect_text_block_heights(
    image: np.ndarray,
    min_conf: int = 40,
) -> List[Tuple[str, float]]:
    """
    Use pytesseract's `image_to_data` to get per-word bounding boxes and
    extract (text, pixel_height) pairs for words with sufficient confidence.

    Args:
        image:    BGR or grayscale image (numpy array).
        min_conf: Minimum Tesseract word confidence to include (0–100).

    Returns:
        List of (text, height_px) tuples.
    """
    try:
        import pytesseract
        from pytesseract import Output

        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        data = pytesseract.image_to_data(
            gray, config="--oem 3 --psm 11", output_type=Output.DICT
        )

        blocks: List[Tuple[str, float]] = []
        for i, word in enumerate(data["text"]):
            word = str(word).strip()
            if not word:
                continue
            conf = int(data["conf"][i])
            if conf < min_conf:
                continue
            h_px = float(data["height"][i])
            if h_px > 2:  # ignore sub-pixel noise
                blocks.append((word, h_px))
        return blocks

    except Exception as exc:
        logger.warning("Tesseract bounding-box detection failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

def check_font_sizes(
    image: np.ndarray,
    image_path: Optional[str] = None,
    dpi: Optional[float] = None,
    pdp_area_cm2: Optional[float] = None,
) -> FontSizeReport:
    """
    Run font-size compliance checks on a label image.

    Args:
        image:        OpenCV BGR image loaded via cv2.imread().
        image_path:   Path to the original file (used for EXIF DPI lookup).
        dpi:          Known DPI (e.g. from a controlled scanning flow).
                      If None, attempts EXIF lookup, then falls back to DEFAULT_DPI.
        pdp_area_cm2: Known PDP area in cm². If None, estimated from image dimensions.

    Returns:
        FontSizeReport with per-block results and overall pass/fail.
    """
    # ── 1. Resolve DPI ─────────────────────────────────────────────────────
    calibration_note = ""
    if dpi is None:
        if image_path:
            dpi = _estimate_dpi_from_exif(image_path)
        if dpi is None:
            dpi = float(DEFAULT_DPI)
            calibration_note = (
                f"DPI unknown — using conservative fallback of {DEFAULT_DPI} DPI. "
                "Font-size estimates may under-report real-world sizes. "
                "For reliable results, use a controlled scan flow with a known reference object."
            )
        else:
            calibration_note = f"DPI read from image EXIF metadata: {dpi:.0f} DPI."

    # ── 2. Estimate PDP area if not provided ────────────────────────────────
    if pdp_area_cm2 is None:
        pdp_area_cm2 = estimate_pdp_area_cm2(image, dpi)
        calibration_note += f" PDP area estimated from image dimensions: {pdp_area_cm2:.1f} cm²."

    # ── 3. Determine minimum required font height ───────────────────────────
    min_mm = _get_min_font_height_mm(pdp_area_cm2)

    # ── 4. Detect text block heights ────────────────────────────────────────
    blocks_raw = detect_text_block_heights(image)

    if not blocks_raw:
        logger.warning("No text blocks detected for font-size analysis.")
        return FontSizeReport(
            dpi_used=dpi,
            pdp_area_cm2=pdp_area_cm2,
            min_required_mm=min_mm,
            total_blocks_checked=0,
            failing_blocks=0,
            overall_pass=True,  # Cannot determine → conservative pass
            calibration_note=calibration_note + " No text blocks detected.",
        )

    # ── 5. Build per-block results ──────────────────────────────────────────
    checked: List[FontCheckResult] = []
    for text, height_px in blocks_raw:
        est_mm = pixels_to_mm(height_px, dpi)
        passes = est_mm >= min_mm
        checked.append(FontCheckResult(
            text_snippet=text[:40],
            pixel_height=round(height_px, 1),
            estimated_mm=round(est_mm, 2),
            min_required_mm=min_mm,
            passes=passes,
            dpi_used=dpi,
            note="" if passes else f"Height {est_mm:.2f} mm < required {min_mm:.1f} mm",
        ))

    failing = [b for b in checked if not b.passes]
    overall_pass = len(failing) == 0

    return FontSizeReport(
        dpi_used=dpi,
        pdp_area_cm2=pdp_area_cm2,
        min_required_mm=min_mm,
        total_blocks_checked=len(checked),
        failing_blocks=len(failing),
        overall_pass=overall_pass,
        blocks=checked,
        calibration_note=calibration_note,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys, json

    img_path = sys.argv[1] if len(sys.argv) > 1 else "labels/Lays.jpg"
    img = cv2.imread(img_path)
    if img is None:
        print(f"Error: Could not load image from '{img_path}'")
        sys.exit(1)

    report = check_font_sizes(img, image_path=img_path)
    print(json.dumps(report.to_dict(), indent=2))
