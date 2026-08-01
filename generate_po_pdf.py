"""
generate_po_pdf.py
-------------------
One-off script to generate samples/purchase_order_1.pdf - a real PDF file
(not just .txt) so the agent's PDF-reading path is demonstrated too.
Run once: python generate_po_pdf.py
"""

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

OUT_PATH = "samples/purchase_order_1.pdf"

c = canvas.Canvas(OUT_PATH, pagesize=letter)
width, height = letter

lines = [
    ("Helvetica-Bold", 16, "NORTHWIND TRADERS - PURCHASE ORDER"),
    ("Helvetica", 10, ""),
    ("Helvetica", 11, "PO Number: PO-55321"),
    ("Helvetica", 11, "Date: 2025-06-20"),
    ("Helvetica", 11, "Vendor: Pacific Paper Co."),
    ("Helvetica", 11, "Ship To: Northwind Traders, 90 Harbor Rd, Seattle, WA"),
    ("Helvetica", 10, ""),
    ("Helvetica-Bold", 11, "Item              Qty    Unit Price    Amount"),
    ("Helvetica", 11, "A4 Paper (ream)    100    2.50           250.00"),
    ("Helvetica", 11, "Toner Cartridge    8      45.00          360.00"),
    ("Helvetica", 11, "Envelopes (box)    20     6.00           120.00"),
    ("Helvetica", 10, ""),
    ("Helvetica", 11, "Subtotal: 730.00"),
    ("Helvetica", 11, "Tax: 58.40"),
    ("Helvetica", 11, "Discount: 30.00"),
    ("Helvetica", 11, "Total: 758.40"),
    ("Helvetica", 9, ""),
    ("Helvetica-Oblique", 9, "Approved by procurement dept. Currency: USD"),
]

y = height - 60
for font, size, text in lines:
    c.setFont(font, size)
    c.drawString(50, y, text)
    y -= 20

c.save()
print(f"Created {OUT_PATH}")
