#!/usr/bin/env python3
"""Standalone tester for Marex detection and extraction.

Run this script from the project root. It prints issuer detection results for
several sender variants and then tries to extract a DataFrame from the Marex
HTML file (default path is the attachment path). Change the HTML path if needed.

Usage:
  python test_marex.py [path/to/marex-file.htm]
"""
from __future__ import annotations

import sys
from pathlib import Path

from app_core.extractors import detect_issuer_from_sender, extract_for_sender


def test_detection() -> None:
    senders = [
        "marex",
        "Marex",
        "agile@marexfp.com",
        "Agile Marex",
        "agile",
        "someone@other.com",
    ]
    print("--- Issuer detection tests ---")
    for s in senders:
        print(f"{s!r} -> {detect_issuer_from_sender(s)!r}")
    print()


def test_extraction(html_path: str | Path) -> None:
    p = Path(html_path)
    if not p.exists():
        print(f"HTML file not found: {p}")
        return

    raw = p.read_bytes()
    html = None
    # Marex templates can be plain HTML or Word/UTF-16 generated. Also support TSV fallback.
    for enc in ("utf-8", "utf-16", "utf-16-le", "cp1252", "latin-1"):
        try:
            cand = raw.decode(enc)
        except Exception:
            continue
        lowered = cand.lower()
        if "<table" in lowered or "\t" in cand or "marex" in lowered:
            html = cand
            print(f"Decoded HTML using encoding: {enc}")
            break
    if html is None:
        html = raw.decode("latin-1", errors="ignore")
        print("Decoded HTML using fallback latin-1")

    senders = ["marex", "agile@marexfp.com", "Marex"]
    print(f"--- Extraction tests using file: {p} ---")
    for s in senders:
        df, issuer = extract_for_sender(html, s)
        print(f"Sender={s!r} => detected issuer={issuer!r}")
        if df is None:
            print("  No dataframe extracted.")
        else:
            try:
                import pandas as pd

                print(f"  Extracted DataFrame shape={df.shape}")
                print("  Columns:", list(df.columns))
                print("  First rows:")
                print(df.head(8).to_string(index=False))
            except Exception:
                print("  Extracted object (non-DataFrame):", type(df))
    print()


def main() -> None:
    test_detection()

    if len(sys.argv) > 1:
        html_path = sys.argv[1]
    else:
        html_path = r"C:\Users\yann.boulbenmeyer\OneDrive - Calebo Capital AG\Dokumente\Projects\Pricer Templates\Marex\RE @agile.htm"

    test_extraction(html_path)


if __name__ == "__main__":
    main()
