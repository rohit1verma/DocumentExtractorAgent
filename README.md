# Document Data Extractor Agent

An AI agent that reads messy business documents (invoices, receipts, purchase
orders — PDF, image, or text) and extracts clean, validated, structured JSON.

**Input:** a document (PDF/Image/TXT)
**Output:** structured JSON (vendor, dates, line items, totals) + a sanity-check
validation report

Built for the Rooman AI Challenge — Category 2: Document Data Extractor.

---

## How it works (the loop)

User gives a file path
↓
.pdf / .txt → extract text (pdfplumber) → send text to a text LLM
.jpg / .png → send image directly to a vision-capable LLM
↓
Model returns structured JSON per a fixed schema
↓
Parse the model's JSON reply into a validated Pydantic schema
↓
Run 5 sanity checks (math, dates, required fields, negatives)
↓
Print + save result as JSON in outputs/


**Supported inputs:** `.pdf`, `.txt`, `.jpg`/`.jpeg`, `.png`, `.webp`.

If no API key is configured, `.pdf`/`.txt` documents fall back to a small
offline regex extractor so the text pipeline is still runnable with zero
setup (see [Tradeoffs](#tradeoffs--known-limitations)). **Images have no
offline fallback** — accurate extraction from a photo genuinely needs either
a vision model or OCR, so image files require a real `OPENROUTER_API_KEY`
and will raise a clear error without one.

---

## 1. Setup

### Clone and install

```bash
git clone <your-repo-url>
cd doc-extractor-agent
pip install -r requirements.txt
```

### Get a free OpenRouter API key

OpenRouter (https://openrouter.ai) gives one API key that works across many
models, including several **free** ones — no card required.

1. Go to https://openrouter.ai and sign in (Google/GitHub/email).
2. Go to https://openrouter.ai/keys → **Create Key** → copy it
   (starts with `sk-or-v1-...`).
3. Go to https://openrouter.ai/models, filter by **Prompt pricing: Free**,
   and pick a model if you want to swap from the defaults below.

This project uses two separate free models:
- **Text documents** (.pdf/.txt) → `nvidia/nemotron-3-ultra-550b-a55b:free`
  — a 550B-parameter (55B active, MoE) reasoning model, text-only, 1M
  context window. Strong at structured extraction from long documents.
- **Image documents** (.jpg/.png) → `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`
  — a multimodal model that accepts text, image, video, and audio input,
  used here purely for its vision capability.

### Configure the key

```bash
cp .env.example .env
```

Edit `.env`:

OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
OPENROUTER_VISION_MODEL=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free


That's it — `agent.py` loads `.env` automatically via `python-dotenv`.

> **Note:** OpenRouter's free-tier lineup changes frequently — models get
> delisted or renamed without much notice. If either model above returns a
> `404 - No endpoints found` error, go to https://openrouter.ai/models,
> filter by **Free**, and swap in a current model ID (filter by the
> **Vision** capability tag for the image model). This is exactly why both
> model names live in `.env` rather than being hardcoded.

---

## 2. Run it

**Single document:**
```bash
python agent.py samples/invoice_1.txt
```

**Image (photo/scan of a receipt, invoice, etc.):**
```bash
python agent.py path/to/your/receipt.jpg
```
This requires `OPENROUTER_API_KEY` to be set — it's sent to the vision-capable
model configured as `OPENROUTER_VISION_MODEL` in `.env`.

**Every sample document at once:**
```bash
python agent.py --batch samples/
```

**Interactive mode (no arguments):**
```bash
python agent.py
# Document path: samples/receipt_1.txt
# Document path: samples/purchase_order_1.pdf
# Document path: quit
```

Each run prints the JSON result to the console and saves it to
`outputs/<filename>.json`.

---

## 3. Sample inputs & outputs (included in this repo)

| File | Layout | Notes |
|---|---|---|
| `samples/invoice_1.txt` | Invoice, itemized table | Clean, well-formed |
| `samples/invoice_2_messy.txt` | Invoice, GST/INR layout | Different currency, terminology (Sub Total / GST) |
| `samples/receipt_1.txt` | Retail receipt, `qty x item ..... price` layout | **Contains an intentional total error** to demonstrate validation catching it |
| `samples/purchase_order_1.pdf` | Purchase order, actual PDF | Tests real PDF text extraction, not just .txt |
| `samples/restimages.jpg` | Photographed receipt | Tests the vision extraction path |

Every sample above has a corresponding extracted JSON already saved in
`outputs/` from a test run, so you can inspect expected output shape without
running anything.

**Example output shape** (`outputs/invoice_1.json`, structure abbreviated):
```json
{
  "source_file": "invoice_1.txt",
  "extracted_data": {
    "document_type": "invoice",
    "document_id": "INV-2024-0091",
    "date": "2024-03-14",
    "vendor_name": "ACME INDUSTRIAL SUPPLIES",
    "line_items": [
      {"description": "Steel Pipes (2in)", "quantity": 40, "unit_price": 12.5, "amount": 500.0}
    ],
    "subtotal": 855.0,
    "tax": 85.5,
    "shipping": 20.0,
    "total": 960.5,
    "currency": "USD"
  },
  "validation_report": {
    "checks": [ { "name": "...", "status": "pass|warning|fail", "detail": "..." } ],
    "summary": { "passed": 5, "warnings": 0, "failed": 0, "total_checks": 5 }
  }
}
```

> **Note on the JSON currently sitting in `outputs/`:** the .txt/.pdf samples
> were originally generated *without* an API key set (offline fallback mode),
> so you can see the pipeline runs end-to-end out of the box. Once
> `OPENROUTER_API_KEY` is set and the agent is re-run, extraction accuracy
> improves substantially — the fallback intentionally misses fields the LLM
> catches easily (see Tradeoffs). The image sample was run with a real key,
> since images have no offline fallback path.

---

## 4. Validation logic

Every extraction gets 5 automated sanity checks (`extractor/validator.py`).
Checks never block output — a failing check is reported, not hidden, so a
human reviewer knows exactly what to double check:

1. **`line_items_sum_matches_subtotal`** — do the extracted line item
   amounts add up to the subtotal (or total, if no subtotal field exists)?
2. **`subtotal_tax_shipping_discount_equals_total`** — does
   `subtotal + tax + shipping - discount == total` (within 2 cents)?
3. **`date_is_valid`** — does the extracted date string actually parse to a
   real calendar date (via `dateutil`), and is it not implausibly in the future?
4. **`required_fields_present`** — are `document_type`, `document_id`, and
   `total` present at all?
5. **`no_unexpected_negative_amounts`** — flags (doesn't fail) negative line
   item amounts, since these can be legitimate refunds/discounts.

Each check reports `pass`, `warning`, `fail`, or `skipped` (when there isn't
enough data to check, e.g. no line items were found at all).

`samples/receipt_1.txt` was deliberately written with a $1.00 total error
(`Subtotal $14.75 + Tax $1.25` should be `$16.00`, but the receipt prints
`$17.00`) to demonstrate check #2 catching a real-world data-entry mistake.

---

## 5. Project structure

doc-extractor-agent/
├── agent.py # CLI entry point / the input-think-act-output loop
├── extractor/
│ ├── schema.py # Pydantic schema (the JSON contract)
│ ├── pdf_reader.py # PDF/TXT → raw text
│ ├── llm_client.py # OpenRouter call (text + vision) + fallback trigger
│ ├── fallback_extractor.py # Offline regex extractor (zero-setup demo path)
│ └── validator.py # 5 sanity checks
├── samples/ # Sample documents across text, PDF, and image inputs
├── outputs/ # Saved JSON results (pre-populated from test runs)
├── generate_po_pdf.py # One-off script used to create the sample PDF
├── requirements.txt
├── .env.example
└── README.md


---

## Tradeoffs & known limitations

**Model choice — OpenRouter free tier over paid APIs.**
Chosen so anyone can reproduce the demo with zero cost. Tradeoff: free
models are less reliable than e.g. GPT-4/Claude-class paid models on
edge-case layouts, and OpenRouter's free model lineup/rate limits can change
over time — the model names are config variables (`OPENROUTER_MODEL` and
`OPENROUTER_VISION_MODEL`) specifically so it's a one-line swap if a given
free model gets deprecated or rate-limited.

**This actually happened during development.** The vision model originally
configured (`google/gemini-2.0-flash-exp:free`) was delisted from
OpenRouter's free tier partway through the project, producing a
`404 - No endpoints found` error. It was replaced with
`nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`. This is real evidence
of the risk noted above, not a hypothetical — anyone maintaining this agent
long-term should expect to periodically re-check
https://openrouter.ai/models for free-tier changes, or switch to
OpenRouter's `openrouter/free` auto-routing alias, which selects a working
free model automatically based on the request's requirements (e.g. needing
image input).

**Text extraction, not vision, for PDFs.**
`pdf_reader.py` uses `pdfplumber` to extract text, then sends that text to
the text LLM — it does not send PDF page images to a vision model. This is
faster, cheaper, and works well for the vast majority of invoices/receipts/POs,
which are text-based PDFs. **Known failure case:** scanned/photographed PDFs
with no embedded text layer will raise a clear error rather than silently
returning empty data. With more time, I'd route image-heavy PDFs through the
same vision path already built for `.jpg`/`.png` files, or add an OCR
pre-pass (e.g. Tesseract).

**Offline regex fallback exists only for zero-setup demoing (text/PDF only).**
If `OPENROUTER_API_KEY` isn't set, `fallback_extractor.py` kicks in for
`.txt`/`.pdf` files so reviewers can `git clone` and run `python agent.py`
immediately with no signup. It is intentionally simple (first line as
vendor name, basic money-pattern regex) and is measurably worse than the LLM
path — compare the sample outputs in `outputs/` generated in fallback mode
against results after adding a real key. **No such fallback exists for
images** — a regex can't read a photo, so image files require a real API
key and fail with a clear error message otherwise. This tradeoff was made
deliberately: a reviewer with zero setup time still sees a working
end-to-end text pipeline, while full extraction quality (and all image
support) is one `.env` edit away.

**Validation reports rather than rejects.**
A failed sanity check doesn't stop the agent from returning data — it
annotates the output instead. For a real accounting workflow you'd likely
want a stricter mode that quarantines documents failing critical checks
(e.g. total math) for manual review before they enter a database.

**No layout-specific parsers.**
Rather than writing a separate parser per document type (invoice vs.
receipt vs. PO), one general schema + one prompt handles all three — this
is what "handle at least two different layouts" is demonstrating here (in
practice, multiple layouts across three document types, plus an image
input). Tradeoff: a single general-purpose prompt is less tuned than a
bespoke parser per vendor template would be, but generalizes far better to
documents never seen before.

**What I'd improve with more time:**
- OCR pre-pass for scanned/photographed PDFs (currently only loose image
  files get the vision path).
- A confidence score per field, not just a binary pass/fail per check.
- A small eval set (20+ documents with hand-labeled ground truth) to
  actually measure field-level accuracy rather than eyeballing outputs.
- A lightweight web UI (drag-and-drop a file, see JSON + validation side by side).
- Currency-aware number parsing (e.g. `1.234,56` EU-style decimals).
- Auto-fallback through a list of free models if the configured one 404s,
  instead of requiring a manual `.env` edit.

---

## Design choices at a glance

| Decision | Why |
|---|---|
| Python + OpenRouter (OpenAI-compatible SDK) | Free tier, standard library, minimal glue code |
| Two separate model configs (text vs. vision) | Nemotron Ultra is text-only; images need a genuinely multimodal model |
| Pydantic for the schema | Guarantees the LLM's JSON reply is actually well-typed before it's trusted |
| pdfplumber over PyPDF2 | Better text layout preservation for tabular invoice data |
| One schema for all doc types | Simpler code path; `document_type` field disambiguates downstream |
| Fallback extractor (text/PDF only) | Makes the repo runnable in under 2 minutes with zero signup |