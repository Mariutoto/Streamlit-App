#!/usr/bin/env python3
"""Standalone tester for Morgan Stanley (MS) via Outlook only.

Usage:
  python test_ms.py "Your Mailbox" "Inbox/Pricer" [max_emails]
  # or (equivalent)
  python test_ms.py outlook "Your Mailbox" "Inbox/Pricer" [max_emails]

Prints issuer detection results (implicit in pipeline) and the extracted rows
for issuer 'ms' from the specified Outlook folder.
"""
from __future__ import annotations

import sys
import pandas as pd

from app_core.extractors import detect_issuer_from_sender, extract_for_sender
from app_core.pipeline import run_outlook, run_on_html


def _parse_folder_arg(arg: str) -> list[str]:
    # Accept formats like "Inbox", "Inbox/Pricer", "Inbox>Pricer", "Inbox\\Pricer"
    for sep in ("/", ">", "\\"):
        if sep in arg:
            return [p for p in arg.split(sep) if p]
    return [arg]


def run_outlook_ms(mailbox: str, folder_path: list[str], max_emails: int = 60) -> None:
    df, stats = run_outlook(mailbox, folder_path, max_emails=max_emails)
    if df is None or df.empty:
        print(f"No rows parsed from Outlook. Stats={stats}")
        return
    cand = df[df["issuer"].astype(str).str.lower().eq("ms")]
    if cand.empty:
        print(f"Parsed {stats['retrieved_emails']} emails but none for MS. Stats={stats}")
        print(df.head(8).to_string(index=False))
        return
    print(f"Parsed {len(cand)} MS rows from Outlook. Stats={stats}")
    print("Columns:", list(cand.columns))
    print(cand.head(12).to_string(index=False))


def main() -> None:
    # Support both forms:
    #   python test_ms.py outlook "Mailbox" "Inbox/Pricer" [max]
    #   python test_ms.py "Mailbox" "Inbox/Pricer" [max]
    argv = [a for a in sys.argv[1:]]
    if not argv:
        print("Usage: python test_ms.py \"Mailbox\" \"Inbox/Pricer\" [max_emails]")
        return
    if argv[0].lower() == "outlook":
        argv = argv[1:]
    mailbox = argv[0] if len(argv) >= 1 else ""
    folder = argv[1] if len(argv) >= 2 else "Inbox"
    max_emails = int(argv[2]) if len(argv) >= 3 else 60
    if not mailbox:
        print("Provide mailbox display name or SMTP as first argument.")
        return
    run_outlook_ms(mailbox, _parse_folder_arg(folder), max_emails=max_emails)


if __name__ == "__main__":
    main()
