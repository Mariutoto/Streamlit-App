from __future__ import annotations

import argparse
import pathlib
from typing import Iterable, Tuple

import pandas as pd

from app_core.extractors import detect_issuer_from_sender, extract_for_sender
from app_core.pipeline import run_on_html

ENCODINGS = ["utf-8", "utf-16", "utf-16-le", "cp1252", "latin-1"]
DEFAULT_SENDER = "Morgan.Stanley.Swiss@morganstanley.com"


def try_decode(path: pathlib.Path, encs: Iterable[str] = ENCODINGS) -> Tuple[str | None, str | None]:
    data = path.read_bytes()
    for enc in encs:
        try:
            return enc, data.decode(enc)
        except Exception:
            continue
    return None, None


def summarize_df(df: pd.DataFrame, prefix: str = "") -> None:
    if df is None or df.empty:
        print(f"{prefix}DataFrame is empty.")
        return
    print(f"{prefix}shape={df.shape} columns={list(df.columns)}")
    print(df.head(5).to_string(index=False))


def debug_single_html(html: str, sender: str) -> None:
    detected = detect_issuer_from_sender(sender)
    print(f"  sender -> issuer: {detected!r}")
    extractor_df, extractor_issuer = extract_for_sender(html, sender)
    if extractor_df is None:
        print("  extractor returned None")
        return
    print(f"  extractor issuer: {extractor_issuer!r} rows={len(extractor_df)}")
    summarize_df(extractor_df, prefix="  raw ")
    normalized = run_on_html(html, sender)
    if normalized is None or normalized.empty:
        print("  normalize() returned no rows")
    else:
        print(f"  normalize() rows={len(normalized)}")
        summarize_df(normalized, prefix="  norm ")


def iter_paths(arg: str) -> list[pathlib.Path]:
    p = pathlib.Path(arg)
    if p.is_file():
        return [p]
    if p.is_dir():
        return sorted([q for q in p.glob("**/*") if q.suffix.lower() in {".htm", ".html"}])
    raise FileNotFoundError(p)


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug Morgan Stanley HTML variants.")
    parser.add_argument("paths", nargs="+", help="HTML file(s) or directory containing MS emails.")
    parser.add_argument("--sender", default=DEFAULT_SENDER, help="Override sender used for detection.")
    args = parser.parse_args()

    files: list[pathlib.Path] = []
    for arg in args.paths:
        files.extend(iter_paths(arg))
    if not files:
        print("No HTML files found.")
        return

    for idx, path in enumerate(files, 1):
        enc, html = try_decode(path)
        print(f"\n=== [{idx}/{len(files)}] {path} (encoding={enc}) ===")
        if not html:
            print("  Unable to decode file with tested encodings.")
            continue
        try:
            debug_single_html(html, args.sender)
        except Exception as exc:
            print(f"  Error while processing: {exc!r}")


if __name__ == "__main__":
    main()
