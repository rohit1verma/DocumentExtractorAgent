"""
pdf_reader.py
-------------
Turns a source document (PDF or .txt) into raw text that can be fed to the LLM.

Design choice: for this challenge we extract text (via pdfplumber) rather than
sending raw images to a vision model. This keeps the agent free-tier-friendly
(OpenRouter's free text models are more reliable than free vision models) and
works well because invoices/receipts/POs are almost always text-based PDFs,
not scans. See README "Tradeoffs" section for the scanned-image limitation.
"""

import os
import pdfplumber


def read_document(path: str) -> str:
    """Read a PDF or plain text file and return its raw text content."""
    ext = os.path.splitext(path)[1].lower()

    if ext == ".pdf":
        return _read_pdf(path)
    elif ext in (".txt", ".text"):
        return _read_txt(path)
    else:
        raise ValueError(
            f"Unsupported file type '{ext}'. Supported: .pdf, .txt "
            f"(images can be OCR'd first with an external tool, then passed as .txt)"
        )


def _read_pdf(path: str) -> str:
    text_parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    text = "\n".join(text_parts).strip()
    if not text:
        raise ValueError(
            f"No extractable text found in '{path}'. It may be a scanned "
            f"image PDF — this agent needs OCR'd/text-based PDFs (see README)."
        )
    return text


def _read_txt(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
