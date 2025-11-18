#!/usr/bin/env python3
"""Standalone tester for JPM, Morgan (MS) and UBS detection & extraction.

Run from project root. Prints detection results for common sender strings and
attempts to extract DataFrames from provided HTML templates. You can pass file
paths as command line arguments in the order: jpm_path ubs_path morgan_path
"""
from __future__ import annotations

import sys
from pathlib import Path

from app_core.extractors import detect_issuer_from_sender, extract_for_sender
from app_core.pipeline import run_outlook


def decode_html_try_paths(p: Path) -> str | None:
    if not p.exists():
        return None
    raw = p.read_bytes()
    for enc in ("utf-8", "utf-16", "utf-16-le", "cp1252", "latin-1"):
        try:
            cand = raw.decode(enc)
        except Exception:
            continue
        # quick sanity check
        if "<table" in cand.lower() or "product" in cand.lower() or "price" in cand.lower():
            print(f"Decoded {p} using {enc}")
            return cand
    # fallback
    try:
        return raw.decode("latin-1", errors="ignore")
    except Exception:
        return None


def run_one(path: str | Path, sender_candidates: list[str]) -> None:
    p = Path(path)
    if not p.exists():
        print(f"File not found: {p}")
        return
    html = decode_html_try_paths(p)
    if html is None:
        print(f"Could not decode file: {p}")
        return

    print(f"\n--- Testing file: {p} ---")
    for s in sender_candidates:
        df, issuer = extract_for_sender(html, s)
        print(f"Sender={s!r} -> detected issuer={issuer!r}")
        if df is None:
            print("  No dataframe extracted.")
        else:
            try:
                print(f"  Extracted DataFrame shape={df.shape}")
                print("  Columns:", list(df.columns)[:10], "...")
                print(df.head(4).to_string(index=False))
            except Exception as e:
                print("  Extracted object type:", type(df), "error printing:", e)


def _parse_folder_arg(arg: str) -> list[str]:
    for sep in ("/", ">", "\\"):
        if sep in arg:
            return [p for p in arg.split(sep) if p]
    return [arg]


def run_outlook_issuers(mailbox: str, folder: list[str], issuers: list[str], max_emails: int = 60) -> None:
    df, stats = run_outlook(mailbox, folder, max_emails=max_emails)
    if df is None or df.empty:
        print(f"No rows parsed from Outlook. Stats={stats}")
        return
    want = set(x.lower() for x in issuers)
    cand = df[df["issuer"].astype(str).str.lower().isin(want)]
    if cand.empty:
        print(f"Parsed rows but none for {issuers}. Stats={stats}")
        print(df.head(8).to_string(index=False))
        return
    print(f"Parsed {len(cand)} rows for {issuers} from Outlook. Stats={stats}")
    print(cand.head(12).to_string(index=False))


def main() -> None:
    # Outlook mode:
    #   python test_jpm_morgan_ubs.py outlook "My Mailbox" "Inbox/Pricer"
    # File mode (default for quick debugging):
    #   python test_jpm_morgan_ubs.py [jpm_file] [ubs_file] [ms_file]

    if len(sys.argv) >= 2 and sys.argv[1].lower() == "outlook":
        mailbox = sys.argv[2] if len(sys.argv) > 2 else ""
        folder = sys.argv[3] if len(sys.argv) > 3 else "Inbox"
        if not mailbox:
            print("Provide mailbox display name or SMTP as arg2.")
            return
        run_outlook_issuers(mailbox, _parse_folder_arg(folder), issuers=["jpm", "ubs", "ms"], max_emails=80)
        return

    # default paths from attachments (change if needed)
    default_jpm = r"C:\Users\yann.boulbenmeyer\OneDrive - Calebo Capital AG\Dokumente\Projects\Pricer Templates\JP Morgan Template\Many Price JP Morgan.htm"
    default_ubs = r"C:\Users\yann.boulbenmeyer\OneDrive - Calebo Capital AG\Dokumente\Projects\Pricer Templates\UBS Template\UBS Many ones.htm"
    default_morgan = None  # provide if you have a Morgan file

    jpm_path = sys.argv[1] if len(sys.argv) > 1 else default_jpm
    ubs_path = sys.argv[2] if len(sys.argv) > 2 else default_ubs
    morgan_path = sys.argv[3] if len(sys.argv) > 3 else default_morgan

    # detection candidates
    jpm_senders = ["jpm", "jpmorgan", "JPM Markets", "quotation@jpm.com"]
    ubs_senders = ["ubs", "ol-rmp-marketaccess-ep@ubs.com", "OL-GED-EmailPricer@ubs.com"]
    morgan_senders = ["morganstanley", "morgan.stanley.swiss", "Morgan Stanley"]

    if jpm_path:
        run_one(jpm_path, jpm_senders)
    if ubs_path:
        run_one(ubs_path, ubs_senders)
    if morgan_path:
        run_one(morgan_path, morgan_senders)


if __name__ == "__main__":
    main()
