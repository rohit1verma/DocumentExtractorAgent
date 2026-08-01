"""
schema.py
---------
Defines the structured output contract for the Document Data Extractor agent.

Every document (invoice, receipt, or purchase order) is coerced into this
single schema so downstream code (validation, storage, reporting) doesn't
need to care which layout the source document used.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class LineItem(BaseModel):
    description: str = Field(default="", description="What the line item is")
    quantity: Optional[float] = Field(default=None, description="Units purchased")
    unit_price: Optional[float] = Field(default=None, description="Price per unit")
    amount: Optional[float] = Field(default=None, description="quantity * unit_price, or the line total as printed")


class ExtractedDocument(BaseModel):
    document_type: str = Field(description="One of: invoice, receipt, purchase_order, unknown")
    document_id: Optional[str] = Field(default=None, description="Invoice #, receipt #, PO #, etc.")
    date: Optional[str] = Field(default=None, description="ISO 8601 date, YYYY-MM-DD, if determinable")
    vendor_name: Optional[str] = None
    vendor_address: Optional[str] = None
    customer_name: Optional[str] = None
    customer_address: Optional[str] = None
    line_items: List[LineItem] = Field(default_factory=list)
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    shipping: Optional[float] = None
    discount: Optional[float] = None
    total: Optional[float] = None
    currency: Optional[str] = Field(default=None, description="e.g. USD, INR, EUR")

    @field_validator("document_type")
    @classmethod
    def normalize_doc_type(cls, v: str) -> str:
        v = (v or "unknown").strip().lower().replace(" ", "_")
        if v not in {"invoice", "receipt", "purchase_order", "unknown"}:
            return "unknown"
        return v
