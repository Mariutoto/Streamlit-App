#!/usr/bin/env python3
"""Standalone tester for BBVA detection and extraction.

Run this script from the project root. It prints issuer detection results for
several sender variants and then tries to extract a DataFrame from a BBVA HTML
file (path provided below). Change the HTML path if needed.

Usage:
  python test_bbva.py [path/to/bbva.html]
"""
from __future__ import annotations

import sys
from pathlib import Path

from app_core.extractors import detect_issuer_from_sender, extract_for_sender


def test_detection() -> None:
    senders = [
        "bbva",
        "BBVA",
        "BBVA Markets",
        "BBVA <no-reply@alerts.bbva.com>",
        "no-reply@alerts.bbva.com",
        "alerts@bbva.com",
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
    # Try several encodings (some Word-generated HTML is UTF-16)
    raw = p.read_bytes()
    html = None
    for enc in ("utf-8", "utf-16", "utf-16-le", "cp1252"):
        try:
            cand = raw.decode(enc)
        except Exception:
            continue
        if "<table" in cand.lower() or "mso-normal" in cand.lower():
            html = cand
            print(f"Decoded HTML using encoding: {enc}")
            break
    if html is None:
        # last resort: decode as latin-1
        html = raw.decode("latin-1", errors="ignore")
        print("Decoded HTML using fallback latin-1")

    senders = ["bbva", "BBVA <no-reply@alerts.bbva.com>", "no-reply@alerts.bbva.com"]
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
                # show up to 8 rows
                print(df.head(8).to_string(index=False))
            except Exception:
                print("  Extracted object (non-DataFrame):", type(df))
    print()


def main() -> None:
    test_detection()

    if len(sys.argv) > 1:
        html_path = sys.argv[1]
    else:
        # Default path (update if your BBVA template lives elsewhere)
        html_path = r"C:\Users\yann.boulbenmeyer\OneDrive - Calebo Capital AG\Dokumente\Projects\Pricer Templates\BBVA Template\Re External Indication BRC on SMI SX5E SPX NKY.htm"

    test_extraction(html_path)


if __name__ == "__main__":
    main()
