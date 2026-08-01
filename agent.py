"""
agent.py
--------
Document Data Extractor Agent - CLI entry point.

Usage:
    python agent.py <path-to-document>              # extract one document
    python agent.py --batch samples/                # extract every file in a folder
    python agent.py                                  # interactive loop, asks for a path

For each document this runs the full loop:
    read document -> LLM extraction -> validate -> print + save JSON
"""

import argparse
import json
import os
import sys

from extractor.pdf_reader import read_document
from extractor.llm_client import extract_with_llm, extract_with_llm_vision
from extractor.validator import validate

OUTPUT_DIR = "outputs"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def process_document(path: str) -> dict:
    print(f"\n{'=' * 60}\nProcessing: {path}\n{'=' * 60}")

    is_image = path.lower().endswith(IMAGE_EXTENSIONS)

    if is_image:
        # 1 & 2 combined: the vision model reads the image directly, no
        # separate text-extraction step needed.
        doc = extract_with_llm_vision(path)
    else:
        # 1. Fetch needed data (read the document)
        text = read_document(path)
        # 2. Send prompt + context to the AI model, receive structured answer
        doc = extract_with_llm(text)

    # 3. Validate (sanity checks)
    report = validate(doc)

    # 4. Assemble final output
    result = {
        "source_file": os.path.basename(path),
        "extracted_data": json.loads(doc.model_dump_json()),
        "validation_report": report,
    }

    # 5. Display
    print(json.dumps(result, indent=2))

    # 6. Save
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_name = os.path.splitext(os.path.basename(path))[0] + ".json"
    out_path = os.path.join(OUTPUT_DIR, out_name)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"\n[saved] {out_path}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Document Data Extractor Agent")
    parser.add_argument("path", nargs="?", help="Path to a document (.pdf or .txt)")
    parser.add_argument("--batch", help="Path to a folder of documents to process")
    args = parser.parse_args()

    if args.batch:
        folder = args.batch
        valid_ext = (".pdf", ".txt") + IMAGE_EXTENSIONS
        files = [
            os.path.join(folder, f) for f in sorted(os.listdir(folder))
            if f.lower().endswith(valid_ext)
        ]
        if not files:
            print(f"No .pdf, .txt, or image files found in {folder}")
            sys.exit(1)
        for f in files:
            process_document(f)
        return

    if args.path:
        process_document(args.path)
        return

    # Interactive loop
    print("Document Data Extractor Agent (type a file path, or 'quit' to exit)")
    while True:
        path = input("\nDocument path: ").strip()
        if path.lower() in ("quit", "exit", "q"):
            break
        if not os.path.exists(path):
            print(f"File not found: {path}")
            continue
        process_document(path)


if __name__ == "__main__":
    main()
