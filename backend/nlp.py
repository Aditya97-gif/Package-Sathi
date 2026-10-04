"""
nlp.py — Field extraction for Legal Metrology Compliance Checker.

Three-tier extraction pipeline (cheapest first):
  1. Regex-based pattern matching (fast, no ML)
  2. spaCy NER wrapper (local model)
  3. Ollama mistral:7b LLM fallback (local, no API calls)
"""
from __future__ import annotations

import json
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional Imports (graceful fallback if not installed)
# ---------------------------------------------------------------------------
try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    logger.warning("spaCy not installed. Skipping NER layer.")

try:
    import ollama as _ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger.warning("ollama library not installed. Skipping LLM fallback.")


# ---------------------------------------------------------------------------
# Tier 1 — Regex-Based Field Extraction
# ---------------------------------------------------------------------------

def extract_fields_regex(text: str) -> dict:
    """
    Extract mandatory Legal Metrology declaration fields using regex patterns.
    Returns a dict with keys for each field; value is None if not found.
    """
    fields: dict = {
        "mrp": None,
        "net_quantity": None,
        "mfg_date": None,
        "expiry_date": None,
        "batch_number": None,
        "fssai_license": None,
        "consumer_helpline": None,
        "consumer_email": None,
        "manufacturer_name": None,
        "inclusive_of_taxes": False,
    }

    # ── MRP ──────────────────────────────────────────────────────────────────
    mrp_match = re.search(
        r'(?:M\.?R\.?P\.?|Maximum\s+Retail\s+Price)[^0-9\n]{0,20}[:\-]?\s*'
        r'(?:Rs\.?|₹|INR)?\s*([\d,]+(?:\.\d{1,2})?)',
        text, re.IGNORECASE
    )
    if mrp_match:
        fields["mrp"] = mrp_match.group(1).replace(",", "")

    # ── "Inclusive of all taxes" check ────────────────────────────────────────
    if re.search(r'incl(?:usive)?\s*(?:of)?\s*all\s*taxes', text, re.IGNORECASE):
        fields["inclusive_of_taxes"] = True

    # ── Net Quantity ──────────────────────────────────────────────────────────
    net_match = re.search(
        r'(?:Net\s*(?:Qty\.?|Quantity|Wt\.?|Weight|Content|Volume))\s*[:\-]?\s*\n?\s*'
        r'([\d.]+\s*(?:g|kg|ml|L|l|gm|grams|mg|ltr|litre|litres|Number|Nos?\.?|N|pcs|pieces|units?)(?:\s+of\s+[\d.]+\s*(?:g|kg|ml|L))?)',
        text, re.IGNORECASE
    )
    if net_match:
        fields["net_quantity"] = net_match.group(1).strip()
    else:
        # Standalone weight: "500g" or "1.5 kg" — not preceded by a brand/letter context
        net_standalone = re.search(
            r'(?<!\w)([\d.]+\s*(?:g|kg|ml|L|l|gm))\b(?!\s*(?:of|per|each))',
            text, re.IGNORECASE
        )
        if net_standalone:
            fields["net_quantity"] = net_standalone.group(1).strip()

    # ── Manufacturing Date ────────────────────────────────────────────────────
    mfd_match = re.search(
        r'(?:Month\s*[&and]+\s*Year\s*of\s*(?:Manufacture|Mfg)|'
        r'M(?:f[dr]|anufacture[d]?)\s*(?:Date|Dt\.?)?|PKD|Packed)\s*[:\-]?\s*\n?\s*'
        r'((?:0?[1-9]|1[0-2])[-\/\.](20\d{2}|\d{2})|[A-Za-z]{3}[-\s]\d{2,4})',
        text, re.IGNORECASE
    )
    if not mfd_match:
        mfd_match = re.search(r'\b(0[1-9]|1[0-2])[-\/](20\d{2})\b', text)
    if mfd_match:
        fields["mfg_date"] = mfd_match.group(0).strip()

    # ── Expiry / Best Before ──────────────────────────────────────────────────
    exp_match = re.search(
        r'(?:USE\s*BY|EXP(?:IRY)?(?:\s*DATE)?|BEST\s*BEFORE|BB(?:E|D)?|'
        r'Use\s*Before)\s*[:\-]?\s*\n?\s*'
        r'((?:\d{1,2}[-\/\.]\d{1,2}[-\/\.]\d{2,4})|(?:[A-Za-z]{3}[-\s]\d{2,4})|'
        r'(?:\d+\s*months?))',
        text, re.IGNORECASE
    )
    if not exp_match:
        exp_match = re.search(
            r'((?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)'
            r'\s*months?\s*(?:from\s*(?:manufacture|mfg|packing|pkd|packaging|date\s*of\s*mfg))?)',
            text, re.IGNORECASE
        )
    if exp_match:
        fields["expiry_date"] = exp_match.group(1).strip()

    # ── Batch / Lot Number ────────────────────────────────────────────────────
    batch_match = re.search(
        r'(?:B\.?\s*(?:No\.?|Num\.?)|BATCH\s*(?:No\.?|Num\.?)?|LOT\s*(?:No\.?|Num\.?)?)\s*[:\-]?\s*([A-Za-z0-9\/\-]{2,20})',
        text, re.IGNORECASE
    )
    if batch_match:
        fields["batch_number"] = batch_match.group(1).strip()

    # ── FSSAI License (14 digits) ─────────────────────────────────────────────
    fssai_match = re.search(
        r'(?:FSSAI|Lic(?:ense)?\s*No\.?|Uc\s*No\.?)[^\d]{0,12}(\d{14})',
        text, re.IGNORECASE
    )
    if fssai_match:
        fields["fssai_license"] = fssai_match.group(1)

    # ── Consumer Helpline ─────────────────────────────────────────────────────
    phone_match = re.search(
        r'(?:call|tel(?:ephone)?|toll[\s\-]free|helpline|customer\s*(?:care|service))\s*'
        r'(?:us\s*at)?\s*[:\-]?\s*((?:[0-9][\s\-]?){8,15})',
        text, re.IGNORECASE
    )
    if not phone_match:
        phone_match = re.search(
            r'((?:[0-9][\s\-]?){8,15})\s*\(?Toll[\s\-]Free\)?',
            text, re.IGNORECASE
        )
    if phone_match:
        raw_phone = phone_match.group(1).strip()
        fields["consumer_helpline"] = re.sub(r'\s+', ' ', raw_phone)

    # ── Consumer Email ────────────────────────────────────────────────────────
    email_match = re.search(
        r'[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9.\-]+',
        text
    )
    if email_match:
        fields["consumer_email"] = email_match.group(0)

    # ── Manufacturer Name (heuristic) ─────────────────────────────────────────
    mfr_match = re.search(
        r'(?:Manufactured\s*by|Mfr(?:\.|d)?\s*by|Packed\s*by|Marketed\s*by)\s*[:\-]?\s*\n?\s*(.{5,80})',
        text, re.IGNORECASE
    )
    if mfr_match:
        name_raw = mfr_match.group(1).strip()
        # Take up to the first newline or comma that signals an address
        name_clean = re.split(r'[,\n]', name_raw)[0].strip()
        if len(name_clean) > 3:
            fields["manufacturer_name"] = name_clean

    return fields


# ---------------------------------------------------------------------------
# Tier 2 — spaCy NER Wrapper (local model, optional)
# ---------------------------------------------------------------------------

def _merge_ner_into_fields(fields: dict, text: str) -> dict:
    """
    Uses a local spaCy model to supplement missing fields with NER entities.
    Falls back silently if the model isn't available.
    """
    if not SPACY_AVAILABLE:
        return fields
    try:
        nlp = spacy.load("en_core_web_sm")
        doc = nlp(text[:5000])  # Limit to first 5000 chars for speed
        for ent in doc.ents:
            if ent.label_ == "ORG" and fields["manufacturer_name"] is None:
                fields["manufacturer_name"] = ent.text
            elif ent.label_ == "DATE" and fields["mfg_date"] is None:
                fields["mfg_date"] = ent.text
    except Exception as exc:
        logger.debug("spaCy NER skipped: %s", exc)
    return fields


# ---------------------------------------------------------------------------
# Tier 3 — Ollama mistral:7b LLM Fallback (local, no external API)
# ---------------------------------------------------------------------------

_LLM_PROMPT_TEMPLATE = """You are a Label Compliance AI. Extract the following fields from this product label OCR text.
Return ONLY a valid JSON object (no markdown, no explanation) with exactly these keys:
mrp, net_quantity, mfg_date, expiry_date, batch_number, fssai_license, consumer_helpline, consumer_email, manufacturer_name, inclusive_of_taxes

Rules:
- mrp: numeric string (e.g. "20.00") or null
- net_quantity: string with unit (e.g. "500g", "1 kg", "200 ml") or null
- mfg_date: string (e.g. "05/2025", "Mar 2025") or null
- expiry_date: string or null
- batch_number: string or null
- fssai_license: 14-digit string or null
- consumer_helpline: phone number string or null
- consumer_email: email string or null
- manufacturer_name: string or null
- inclusive_of_taxes: true or false

OCR Text:
---
{ocr_text}
---

JSON:"""


def extract_fields_llm(text: str, model: str = "mistral:7b") -> dict | None:
    """
    Use a local Ollama model to extract fields from OCR text.
    Returns a dict of fields or None if Ollama is not available / fails.
    """
    if not OLLAMA_AVAILABLE:
        logger.info("Ollama not available, skipping LLM extraction.")
        return None
    try:
        prompt = _LLM_PROMPT_TEMPLATE.format(ocr_text=text[:3000])
        response = _ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1, "num_predict": 512},
        )
        raw = response["message"]["content"].strip()
        # Strip any markdown code fences if the model added them
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.IGNORECASE)
        raw = re.sub(r'\s*```$', '', raw)
        parsed = json.loads(raw)
        # Normalise key types
        if "inclusive_of_taxes" in parsed:
            parsed["inclusive_of_taxes"] = bool(parsed["inclusive_of_taxes"])
        return parsed
    except json.JSONDecodeError as exc:
        logger.warning("LLM returned non-JSON output: %s", exc)
    except Exception as exc:
        logger.warning("Ollama call failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Main Entry Point — Three-Tier Pipeline
# ---------------------------------------------------------------------------

def extract_fields(ocr_text: str, use_llm: bool = True, llm_model: str = "mistral:7b") -> tuple[dict, bool]:
    """
    Run the three-tier field extraction pipeline.

    Args:
        ocr_text: Raw text from OCR.
        use_llm: Whether to attempt Ollama LLM fallback for missing fields.
        llm_model: Ollama model name to use.

    Returns:
        (fields_dict, llm_was_used) tuple.
    """
    # Tier 1: Regex
    fields = extract_fields_regex(ocr_text)

    # Tier 2: spaCy NER (supplements missing fields)
    fields = _merge_ner_into_fields(fields, ocr_text)

    # Tier 3: LLM fallback — only if critical fields are still missing
    llm_used = False
    critical_missing = [
        k for k in ("mrp", "net_quantity", "mfg_date")
        if fields.get(k) is None
    ]
    if use_llm and critical_missing:
        logger.info("Critical fields missing %s — trying LLM fallback.", critical_missing)
        llm_fields = extract_fields_llm(ocr_text, model=llm_model)
        if llm_fields:
            llm_used = True
            # Only fill in still-missing fields from LLM result
            for key in fields:
                if fields[key] is None and llm_fields.get(key):
                    fields[key] = llm_fields[key]
            if "inclusive_of_taxes" in llm_fields and not fields["inclusive_of_taxes"]:
                fields["inclusive_of_taxes"] = llm_fields["inclusive_of_taxes"]

    return fields, llm_used
