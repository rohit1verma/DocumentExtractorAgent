"""
fallback_extractor.py
----------------------
A small, deterministic, regex/heuristic based extractor.

This is NOT meant to replace the LLM - it exists so the agent is runnable
end-to-end with zero setup (no API key needed) for quick demos/testing, and
so the pipeline (read -> extract -> validate -> save) is verifiable even
when offline. It handles common patterns across invoices/receipts/POs but
will be far less robust than the LLM path on messy, real-world documents.
"""

import re
from extractor.schema import ExtractedDocument, LineItem

MONEY_RE = r"[-+]?\$?\s?[\d,]+\.\d{2}"


def _to_float(s):
    if s is None:
        return None
    s = s.replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _find(pattern, text, flags=re.IGNORECASE):
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def fallback_extract(text: str) -> ExtractedDocument:
    doc_type = "unknown"
    lower = text.lower()
    if "purchase order" in lower or re.search(r"\bpo\s*#", lower):
        doc_type = "purchase_order"
    elif "receipt" in lower:
        doc_type = "receipt"
    elif "invoice" in lower:
        doc_type = "invoice"

    document_id = _find(r"(?:invoice|receipt|po|order)\s*#?\s*:?\s*([A-Za-z0-9\-]+)", text)
    date = _find(r"date\s*:?\s*([0-9]{1,4}[/-][0-9]{1,2}[/-][0-9]{1,4})", text)
    vendor_name = _find(r"^(.*?)\n", text.strip())  # naive: first line often the vendor/header
    currency = "USD" if "$" in text else _find(r"\b(USD|INR|EUR|GBP)\b", text)

    subtotal = _to_float(_find(rf"sub\s*-?total\s*:?\s*({MONEY_RE})", text))
    tax = _to_float(_find(rf"tax\s*:?\s*({MONEY_RE})", text))
    shipping = _to_float(_find(rf"shipping\s*:?\s*({MONEY_RE})", text))
    discount = _to_float(_find(rf"discount\s*:?\s*({MONEY_RE})", text))
    total = _to_float(_find(rf"(?:grand\s*)?total\s*:?\s*({MONEY_RE})", text))

    line_items = []
    for line in text.splitlines():
        # Heuristic: "Description ... qty x price ... amount"
        m = re.search(
            rf"^(?P<desc>[A-Za-z][A-Za-z0-9 .,\-/]+?)\s+(?P<qty>\d+)\s*(?:x|@)?\s*(?P<price>{MONEY_RE})\s+(?P<amount>{MONEY_RE})\s*$",
            line.strip(),
        )
        if m:
            line_items.append(LineItem(
                description=m.group("desc").strip(),
                quantity=_to_float(m.group("qty")),
                unit_price=_to_float(m.group("price")),
                amount=_to_float(m.group("amount")),
            ))

    return ExtractedDocument(
        document_type=doc_type,
        document_id=document_id,
        date=date,
        vendor_name=vendor_name,
        vendor_address=None,
        customer_name=None,
        customer_address=None,
        line_items=line_items,
        subtotal=subtotal,
        tax=tax,
        shipping=shipping,
        discount=discount,
        total=total,
        currency=currency,
    )
