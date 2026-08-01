"""
test_agent.py
-------------
Offline unit tests for the deterministic parts of the agent: schema
validation and the 5 sanity checks. These don't call the LLM (no API key
needed) so they run instantly and reliably in CI or on any machine.

Run with:
    pip install pytest
    pytest test_agent.py -v
"""

from extractor.schema import ExtractedDocument, LineItem
from extractor.validator import validate


def make_doc(**overrides) -> ExtractedDocument:
    """Build a valid, self-consistent document, then override specific fields."""
    base = dict(
        document_type="invoice",
        document_id="INV-001",
        date="2024-03-14",
        vendor_name="Acme Co",
        line_items=[
            LineItem(description="Widget", quantity=2, unit_price=10.0, amount=20.0),
            LineItem(description="Gadget", quantity=1, unit_price=5.0, amount=5.0),
        ],
        subtotal=25.0,
        tax=2.5,
        shipping=0.0,
        discount=0.0,
        total=27.5,
        currency="USD",
    )
    base.update(overrides)
    return ExtractedDocument(**base)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

def test_schema_accepts_valid_document():
    doc = make_doc()
    assert doc.document_type == "invoice"
    assert len(doc.line_items) == 2


def test_schema_normalizes_unknown_document_type():
    doc = make_doc(document_type="banana")
    assert doc.document_type == "unknown"


def test_schema_normalizes_document_type_casing_and_spacing():
    doc = make_doc(document_type="Purchase Order")
    assert doc.document_type == "purchase_order"


def test_schema_allows_missing_optional_fields():
    doc = ExtractedDocument(document_type="receipt")
    assert doc.total is None
    assert doc.line_items == []


# ---------------------------------------------------------------------------
# Validator tests - line items sum check
# ---------------------------------------------------------------------------

def test_line_items_matching_subtotal_passes():
    doc = make_doc()  # 20 + 5 = 25 = subtotal
    report = validate(doc)
    check = next(c for c in report["checks"] if c["name"] == "line_items_sum_matches_subtotal")
    assert check["status"] == "pass"


def test_line_items_mismatched_subtotal_fails():
    doc = make_doc(subtotal=999.0)
    report = validate(doc)
    check = next(c for c in report["checks"] if c["name"] == "line_items_sum_matches_subtotal")
    assert check["status"] == "fail"


def test_line_items_check_skips_when_no_line_items():
    doc = make_doc(line_items=[])
    report = validate(doc)
    check = next(c for c in report["checks"] if c["name"] == "line_items_sum_matches_subtotal")
    assert check["status"] == "skipped"


# ---------------------------------------------------------------------------
# Validator tests - total math check
# ---------------------------------------------------------------------------

def test_total_math_correct_passes():
    doc = make_doc()  # 25 + 2.5 + 0 - 0 = 27.5 = total
    report = validate(doc)
    check = next(c for c in report["checks"] if c["name"] == "subtotal_tax_shipping_discount_equals_total")
    assert check["status"] == "pass"


def test_total_math_incorrect_fails():
    # Mirrors the intentional bug in samples/receipt_1.txt:
    # subtotal 14.75 + tax 1.25 should total 16.00, but total is set to 17.00
    doc = make_doc(subtotal=14.75, tax=1.25, shipping=0.0, discount=0.0, total=17.00)
    report = validate(doc)
    check = next(c for c in report["checks"] if c["name"] == "subtotal_tax_shipping_discount_equals_total")
    assert check["status"] == "fail"
    assert "17.0" in check["detail"]


def test_total_math_within_rounding_tolerance_passes():
    doc = make_doc(subtotal=25.0, tax=2.5, shipping=0.0, discount=0.0, total=27.51)
    report = validate(doc)
    check = next(c for c in report["checks"] if c["name"] == "subtotal_tax_shipping_discount_equals_total")
    assert check["status"] == "pass"


# ---------------------------------------------------------------------------
# Validator tests - date check
# ---------------------------------------------------------------------------

def test_valid_date_passes():
    doc = make_doc(date="2024-03-14")
    report = validate(doc)
    check = next(c for c in report["checks"] if c["name"] == "date_is_valid")
    assert check["status"] == "pass"


def test_missing_date_warns():
    doc = make_doc(date=None)
    report = validate(doc)
    check = next(c for c in report["checks"] if c["name"] == "date_is_valid")
    assert check["status"] == "warning"


def test_unparseable_date_fails():
    doc = make_doc(date="not a real date at all!!")
    report = validate(doc)
    check = next(c for c in report["checks"] if c["name"] == "date_is_valid")
    assert check["status"] == "fail"


def test_future_date_warns():
    doc = make_doc(date="2099-01-01")
    report = validate(doc)
    check = next(c for c in report["checks"] if c["name"] == "date_is_valid")
    assert check["status"] == "warning"


# ---------------------------------------------------------------------------
# Validator tests - required fields check
# ---------------------------------------------------------------------------

def test_all_required_fields_present_passes():
    doc = make_doc()
    report = validate(doc)
    check = next(c for c in report["checks"] if c["name"] == "required_fields_present")
    assert check["status"] == "pass"


def test_missing_document_id_warns():
    doc = make_doc(document_id=None)
    report = validate(doc)
    check = next(c for c in report["checks"] if c["name"] == "required_fields_present")
    assert check["status"] == "warning"
    assert "document_id" in check["detail"]


# ---------------------------------------------------------------------------
# Validator tests - negative amounts check
# ---------------------------------------------------------------------------

def test_no_negative_amounts_passes():
    doc = make_doc()
    report = validate(doc)
    check = next(c for c in report["checks"] if c["name"] == "no_unexpected_negative_amounts")
    assert check["status"] == "pass"


def test_negative_amount_warns():
    doc = make_doc(line_items=[
        LineItem(description="Refund", quantity=1, unit_price=-10.0, amount=-10.0),
    ])
    report = validate(doc)
    check = next(c for c in report["checks"] if c["name"] == "no_unexpected_negative_amounts")
    assert check["status"] == "warning"
    assert "Refund" in check["detail"]


# ---------------------------------------------------------------------------
# End-to-end validator summary test
# ---------------------------------------------------------------------------

def test_summary_counts_match_check_statuses():
    doc = make_doc()
    report = validate(doc)
    summary = report["summary"]
    statuses = [c["status"] for c in report["checks"]]
    assert summary["passed"] == statuses.count("pass")
    assert summary["warnings"] == statuses.count("warning")
    assert summary["failed"] == statuses.count("fail")
    assert summary["total_checks"] == len(report["checks"])