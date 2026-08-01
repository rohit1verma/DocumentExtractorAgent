"""
llm_client.py
-------------
Talks to an LLM to turn raw document text into structured JSON.

Primary path: OpenRouter (https://openrouter.ai) - free-tier compatible,
OpenAI-style API. Set OPENROUTER_API_KEY in your environment or a .env file.

Fallback path: if no API key is set, we fall back to a small deterministic
regex-based extractor (extractor/fallback_extractor.py) so the agent is still
runnable out-of-the-box for demo/testing purposes without requiring a key.
This fallback is intentionally simple and is NOT a substitute for the LLM -
it exists purely so reviewers can run `python agent.py` with zero setup and
see the full pipeline (read -> extract -> validate -> save) work end to end.
"""

import os
import json
import re
import base64
import mimetypes
from openai import OpenAI
from dotenv import load_dotenv

from extractor.schema import ExtractedDocument
from extractor.fallback_extractor import fallback_extract

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL_NAME = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
# Must be a vision-capable model. Free options change over time - check
# https://openrouter.ai/models (filter: Free) and confirm it lists "image" input.
VISION_MODEL_NAME = os.getenv("OPENROUTER_VISION_MODEL", "google/gemini-2.0-flash-exp:free")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

SYSTEM_PROMPT = """You are a meticulous document data extraction assistant.

Your job: read the raw text of a business document (invoice, receipt, or
purchase order) and extract structured fields into JSON.

Rules:
1. Output ONLY valid JSON. No markdown fences, no commentary, no preamble.
2. Use exactly this schema (omit nothing, use null for unknown values):
{
  "document_type": "invoice | receipt | purchase_order | unknown",
  "document_id": string or null,
  "date": string or null (format as YYYY-MM-DD if possible),
  "vendor_name": string or null,
  "vendor_address": string or null,
  "customer_name": string or null,
  "customer_address": string or null,
  "line_items": [
    {"description": string, "quantity": number or null, "unit_price": number or null, "amount": number or null}
  ],
  "subtotal": number or null,
  "tax": number or null,
  "shipping": number or null,
  "discount": number or null,
  "total": number or null,
  "currency": string or null (e.g. "USD", "INR", "EUR")
}
3. Never invent numbers. If a field truly isn't present in the text, use null.
4. Numbers must be plain numbers (no currency symbols, no commas).
5. If the document layout is unusual, still do your best to map fields into this schema.
"""


def extract_with_llm(document_text: str) -> ExtractedDocument:
    """Send document text to the LLM and parse its JSON reply into ExtractedDocument."""
    if not OPENROUTER_API_KEY:
        print("[info] No OPENROUTER_API_KEY found - using offline fallback extractor. "
              "See README to set up a free OpenRouter key for real LLM extraction.")
        return fallback_extract(document_text)

    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Document text:\n\n{document_text}"},
            ],
        )
        raw = response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[warn] LLM call failed ({e}). Falling back to offline extractor.")
        return fallback_extract(document_text)

    data = _parse_json_safely(raw)
    if data is None:
        print("[warn] Model did not return valid JSON. Falling back to offline extractor.")
        return fallback_extract(document_text)

    try:
        return ExtractedDocument(**data)
    except Exception as e:
        print(f"[warn] Model JSON didn't match schema ({e}). Falling back to offline extractor.")
        return fallback_extract(document_text)


def extract_with_llm_vision(image_path: str) -> ExtractedDocument:
    """Send an image (jpg/png/etc) directly to a vision-capable model and
    parse its JSON reply. No offline fallback exists for images - accurate
    field extraction from a photo/scan genuinely requires either a vision
    model or an OCR engine, neither of which the lightweight regex fallback
    can substitute for."""
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "Image extraction requires an OPENROUTER_API_KEY (no offline "
            "fallback exists for images - see README setup steps)."
        )

    mime_type, _ = mimetypes.guess_type(image_path)
    mime_type = mime_type or "image/jpeg"
    with open(image_path, "rb") as f:
        b64_data = base64.b64encode(f.read()).decode("utf-8")
    data_url = f"data:{mime_type};base64,{b64_data}"

    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)

    try:
        response = client.chat.completions.create(
            model=VISION_MODEL_NAME,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract the fields from this document image."},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        )
        raw = response.choices[0].message.content.strip()
    except Exception as e:
        raise RuntimeError(
            f"Vision model call failed ({e}). The configured model "
            f"'{VISION_MODEL_NAME}' may not support images, or may be "
            f"rate-limited - try a different free vision model via "
            f"OPENROUTER_VISION_MODEL in .env."
        )

    data = _parse_json_safely(raw)
    if data is None:
        raise RuntimeError("Vision model did not return valid JSON for this image.")

    return ExtractedDocument(**data)


def _parse_json_safely(raw: str):
    """Strip markdown fences if the model added them anyway, then parse JSON."""
    cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return None
