"""
rule_engine.py — Legal Metrology Compliance Rule Engine.

Loads `rules/compliance_rules.json` and checks extracted fields
against each mandatory declaration, returning a structured report.
"""
from __future__ import annotations

import json
import os
import re
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path to the versioned rules schema
# ---------------------------------------------------------------------------
RULES_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "rules", "compliance_rules.json"
)


def _load_rules() -> dict:
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Data Classes for Check Results
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    field_id: str
    field_label: str
    status: str          # "pass" | "fail" | "warning" | "skip"
    message: str
    extracted_value: Optional[str] = None
    rule_ref: Optional[str] = None
    severity: str = "error"  # "error" | "warning" | "info"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ComplianceReport:
    overall_status: str          # "compliant" | "non_compliant"
    compliance_score: float      # 0.0 – 100.0
    checks: List[CheckResult] = field(default_factory=list)
    violations: List[CheckResult] = field(default_factory=list)  # only failed checks

    def to_dict(self) -> dict:
        return {
            "overall_status": self.overall_status,
            "compliance_score": round(self.compliance_score, 1),
            "checks": [c.to_dict() for c in self.checks],
            "violations": [v.to_dict() for v in self.violations],
        }


# ---------------------------------------------------------------------------
# Individual Field Checks
# ---------------------------------------------------------------------------

def _check_mrp(fields: dict, rules: dict) -> CheckResult:
    mrp_val = fields.get("mrp")
    inclusive = fields.get("inclusive_of_taxes", False)
    mrp_rules = rules.get("mrp_format_rules", {})

    if not mrp_val:
        return CheckResult(
            field_id="mrp",
            field_label="Maximum Retail Price (MRP)",
            status="fail",
            message="MRP declaration is missing. Rule 6(c) requires MRP inclusive of all taxes.",
            rule_ref="Rule 6(c)",
            severity="error",
        )

    result = CheckResult(
        field_id="mrp",
        field_label="Maximum Retail Price (MRP)",
        status="pass",
        message=f"MRP found: ₹{mrp_val}",
        extracted_value=str(mrp_val),
        rule_ref="Rule 6(c)",
        severity="error",
    )

    if not inclusive:
        result.status = "warning"
        result.message = (
            f"MRP found (₹{mrp_val}) but 'inclusive of all taxes' phrasing not detected. "
            "Rule 6(c) requires the label to state MRP inclusive of all taxes."
        )
        result.severity = "warning"

    return result


def _check_net_quantity(fields: dict, rules: dict) -> CheckResult:
    val = fields.get("net_quantity")
    if not val:
        return CheckResult(
            field_id="net_quantity",
            field_label="Net Quantity",
            status="fail",
            message="Net Quantity is missing. Rule 6(a) requires net quantity in standard SI units.",
            rule_ref="Rule 6(a)",
            severity="error",
        )
    # Validate unit is an accepted SI unit
    accepted = rules.get("mandatory_declarations", [{}])
    nq_rule = next((r for r in accepted if r.get("id") == "net_quantity"), {})
    accepted_units = nq_rule.get("accepted_units", ["g", "kg", "ml", "L", "Number", "N"])
    has_valid_unit = any(
        re.search(rf'\b{re.escape(u)}\b', val, re.IGNORECASE) for u in accepted_units
    )
    if not has_valid_unit:
        return CheckResult(
            field_id="net_quantity",
            field_label="Net Quantity",
            status="warning",
            message=f"Net Quantity found ('{val}') but unit may not conform to SI standards (g, kg, ml, L).",
            extracted_value=val,
            rule_ref="Rule 6(a)",
            severity="warning",
        )
    return CheckResult(
        field_id="net_quantity",
        field_label="Net Quantity",
        status="pass",
        message=f"Net Quantity found: {val}",
        extracted_value=val,
        rule_ref="Rule 6(a)",
        severity="error",
    )


def _check_mfg_date(fields: dict) -> CheckResult:
    val = fields.get("mfg_date")
    if not val:
        return CheckResult(
            field_id="mfg_date",
            field_label="Month & Year of Manufacture",
            status="fail",
            message="Manufacturing/Packing date is missing. Rule 6(e) requires Month & Year of Manufacture.",
            rule_ref="Rule 6(e)",
            severity="error",
        )
    return CheckResult(
        field_id="mfg_date",
        field_label="Month & Year of Manufacture",
        status="pass",
        message=f"Manufacturing date found: {val}",
        extracted_value=val,
        rule_ref="Rule 6(e)",
        severity="error",
    )


def _check_expiry_date(fields: dict) -> CheckResult:
    val = fields.get("expiry_date")
    if not val:
        return CheckResult(
            field_id="expiry_date",
            field_label="Expiry / Best Before Date",
            status="warning",
            message="Expiry/Best Before date not detected. Required for food, pharma, and cosmetic products.",
            rule_ref="Rule 6(f)",
            severity="warning",
        )
    return CheckResult(
        field_id="expiry_date",
        field_label="Expiry / Best Before Date",
        status="pass",
        message=f"Expiry/Best Before date found: {val}",
        extracted_value=val,
        rule_ref="Rule 6(f)",
        severity="warning",
    )


def _check_consumer_care(fields: dict) -> CheckResult:
    phone = fields.get("consumer_helpline")
    email = fields.get("consumer_email")
    if not phone and not email:
        return CheckResult(
            field_id="consumer_care",
            field_label="Consumer Care Contact",
            status="fail",
            message="Consumer care contact (phone or email) is missing. Rule 6(k) requires a consumer care address.",
            rule_ref="Rule 6(k)",
            severity="error",
        )
    contact_parts = []
    if phone:
        contact_parts.append(f"Phone: {phone}")
    if email:
        contact_parts.append(f"Email: {email}")
    return CheckResult(
        field_id="consumer_care",
        field_label="Consumer Care Contact",
        status="pass",
        message=f"Consumer care contact found — {'; '.join(contact_parts)}",
        extracted_value="; ".join(contact_parts),
        rule_ref="Rule 6(k)",
        severity="error",
    )


def _check_fssai(fields: dict) -> CheckResult:
    val = fields.get("fssai_license")
    if not val:
        return CheckResult(
            field_id="fssai_license",
            field_label="FSSAI License Number",
            status="warning",
            message="FSSAI license number not detected. Required for food and beverage products.",
            rule_ref="FSSAI Licensing",
            severity="warning",
        )
    if not re.fullmatch(r'\d{14}', val):
        return CheckResult(
            field_id="fssai_license",
            field_label="FSSAI License Number",
            status="fail",
            message=f"FSSAI license number '{val}' is not 14 digits. FSSAI numbers must be exactly 14 digits.",
            extracted_value=val,
            rule_ref="FSSAI Licensing",
            severity="error",
        )
    return CheckResult(
        field_id="fssai_license",
        field_label="FSSAI License Number",
        status="pass",
        message=f"FSSAI license found: {val}",
        extracted_value=val,
        rule_ref="FSSAI Licensing",
        severity="warning",
    )


def _check_manufacturer(fields: dict) -> CheckResult:
    val = fields.get("manufacturer_name")
    if not val:
        return CheckResult(
            field_id="manufacturer_name",
            field_label="Manufacturer / Packer Name & Address",
            status="fail",
            message="Manufacturer/Packer name and address not detected. Rule 6(b) requires this declaration.",
            rule_ref="Rule 6(b)",
            severity="error",
        )
    return CheckResult(
        field_id="manufacturer_name",
        field_label="Manufacturer / Packer Name & Address",
        status="pass",
        message=f"Manufacturer identified: {val}",
        extracted_value=val,
        rule_ref="Rule 6(b)",
        severity="error",
    )


def _check_batch_number(fields: dict) -> CheckResult:
    val = fields.get("batch_number")
    if not val:
        return CheckResult(
            field_id="batch_number",
            field_label="Batch / Lot Number",
            status="warning",
            message="Batch/Lot number not detected. Recommended for traceability.",
            rule_ref="Rule 6(g)",
            severity="info",
        )
    return CheckResult(
        field_id="batch_number",
        field_label="Batch / Lot Number",
        status="pass",
        message=f"Batch number found: {val}",
        extracted_value=val,
        rule_ref="Rule 6(g)",
        severity="info",
    )


# ---------------------------------------------------------------------------
# Main Rule Engine Entry Point
# ---------------------------------------------------------------------------

def run_compliance_checks(extracted_fields: dict) -> ComplianceReport:
    """
    Run all compliance checks on extracted fields.

    Args:
        extracted_fields: Dict from nlp.extract_fields()

    Returns:
        ComplianceReport with overall status, score, and per-field results.
    """
    rules = _load_rules()
    checks: List[CheckResult] = []

    # Run all checks
    checks.append(_check_manufacturer(extracted_fields))
    checks.append(_check_net_quantity(extracted_fields, rules))
    checks.append(_check_mrp(extracted_fields, rules))
    checks.append(_check_mfg_date(extracted_fields))
    checks.append(_check_expiry_date(extracted_fields))
    checks.append(_check_consumer_care(extracted_fields))
    checks.append(_check_fssai(extracted_fields))
    checks.append(_check_batch_number(extracted_fields))

    # Compute score: each "error" level field is weighted equally
    error_checks = [c for c in checks if c.severity == "error"]
    passed_errors = [c for c in error_checks if c.status == "pass"]
    score = (len(passed_errors) / len(error_checks) * 100) if error_checks else 100.0

    violations = [c for c in checks if c.status in ("fail", "warning")]
    overall = "compliant" if score >= 80 and not any(c.status == "fail" and c.severity == "error" for c in checks) else "non_compliant"

    return ComplianceReport(
        overall_status=overall,
        compliance_score=score,
        checks=checks,
        violations=violations,
    )
