"""
validator.py
------------
Sanity checks run on every extracted document. These don't reject the
extraction - they annotate it with a validation report so a human reviewer
knows exactly what to double check. This is deliberate: for messy real-world
documents, refusing to output anything on a failed check is less useful than
flagging the discrepancy.

Checks implemented:
1. Line items sum ~= subtotal (or total, if no subtotal present)
2. subtotal + tax + shipping - discount ~= total
3. date is a real, parseable calendar date
4. required fields present (document_type, at least one identifying field)
5. no negative amounts in line items (flag, don't fail)
"""

from datetime import datetime
from typing import List, Dict, Any
from dateutil import parser as date_parser

from extractor.schema import ExtractedDocument

TOLERANCE = 0.02  # allow 2 cents of rounding error


def validate(doc: ExtractedDocument) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    checks.append(_check_line_items_sum(doc))
    checks.append(_check_total_math(doc))
    checks.append(_check_date(doc))
    checks.append(_check_required_fields(doc))
    checks.append(_check_negative_amounts(doc))

    passed = sum(1 for c in checks if c["status"] == "pass")
    failed = sum(1 for c in checks if c["status"] == "fail")
    warned = sum(1 for c in checks if c["status"] == "warning")

    return {
        "checks": checks,
        "summary": {
            "passed": passed,
            "warnings": warned,
            "failed": failed,
            "total_checks": len(checks),
        },
    }


def _check_line_items_sum(doc: ExtractedDocument) -> Dict[str, Any]:
    name = "line_items_sum_matches_subtotal"
    if not doc.line_items:
        return {"name": name, "status": "skipped", "detail": "No line items extracted."}

    amounts = [li.amount for li in doc.line_items if li.amount is not None]
    if not amounts:
        return {"name": name, "status": "skipped", "detail": "Line items have no amounts."}

    computed_sum = round(sum(amounts), 2)
    target = doc.subtotal if doc.subtotal is not None else doc.total

    if target is None:
        return {"name": name, "status": "skipped", "detail": "No subtotal/total to compare against."}

    diff = round(abs(computed_sum - target), 2)
    if diff <= TOLERANCE:
        return {"name": name, "status": "pass",
                "detail": f"Line items sum to {computed_sum}, matches {target}."}
    return {"name": name, "status": "fail",
            "detail": f"Line items sum to {computed_sum}, but expected ~{target} (diff {diff})."}


def _check_total_math(doc: ExtractedDocument) -> Dict[str, Any]:
    name = "subtotal_tax_shipping_discount_equals_total"
    if doc.subtotal is None or doc.total is None:
        return {"name": name, "status": "skipped", "detail": "Missing subtotal or total."}

    tax = doc.tax or 0
    shipping = doc.shipping or 0
    discount = doc.discount or 0
    expected_total = round(doc.subtotal + tax + shipping - discount, 2)
    diff = round(abs(expected_total - doc.total), 2)

    if diff <= TOLERANCE:
        return {"name": name, "status": "pass",
                "detail": f"subtotal+tax+shipping-discount = {expected_total}, matches total {doc.total}."}
    return {"name": name, "status": "fail",
            "detail": f"Expected total ~{expected_total}, but document total is {doc.total} (diff {diff})."}


def _check_date(doc: ExtractedDocument) -> Dict[str, Any]:
    name = "date_is_valid"
    if not doc.date:
        return {"name": name, "status": "warning", "detail": "No date extracted."}
    try:
        parsed = date_parser.parse(doc.date, fuzzy=True)
        if parsed > datetime.now():
            return {"name": name, "status": "warning",
                    "detail": f"Date '{doc.date}' is in the future - double check."}
        return {"name": name, "status": "pass", "detail": f"Date '{doc.date}' parses to {parsed.date()}."}
    except (ValueError, OverflowError):
        return {"name": name, "status": "fail", "detail": f"Date '{doc.date}' could not be parsed."}


def _check_required_fields(doc: ExtractedDocument) -> Dict[str, Any]:
    name = "required_fields_present"
    missing = []
    if doc.document_type == "unknown":
        missing.append("document_type")
    if not doc.document_id:
        missing.append("document_id")
    if doc.total is None:
        missing.append("total")

    if not missing:
        return {"name": name, "status": "pass", "detail": "All key identifying fields present."}
    return {"name": name, "status": "warning", "detail": f"Missing/uncertain fields: {', '.join(missing)}."}


def _check_negative_amounts(doc: ExtractedDocument) -> Dict[str, Any]:
    name = "no_unexpected_negative_amounts"
    negatives = [li.description for li in doc.line_items if (li.amount or 0) < 0]
    if not negatives:
        return {"name": name, "status": "pass", "detail": "No negative line item amounts."}
    return {"name": name, "status": "warning",
            "detail": f"Negative amounts found on: {', '.join(negatives)} (could be legitimate refunds/discounts)."}
