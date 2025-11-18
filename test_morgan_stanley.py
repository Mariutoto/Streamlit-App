#!/usr/bin/env python3
"""Morgan Stanley extractor tester.

Preferred usage (reads directly from Outlook, no local HTML file needed):
    python test_morgan_stanley.py outlook "Mailbox Display Name" "Inbox/Pricer" [max_emails]

Legacy file mode (fallback for archived templates):
    python test_morgan_stanley.py path_to_html_file.htm

You can also set PRICER_OUTLOOK_MAILBOX / PRICER_OUTLOOK_FOLDER / PRICER_OUTLOOK_MAX
environment variables to run Outlook mode without command-line arguments.
"""
from __future__ import annotations

import os
import pathlib
import sys
from typing import Iterable, Iterator

import pandas as pd

from app_core.extractors import detect_issuer_from_sender, extract_for_sender
from app_core.email_integration import (
    clean_html_from_mail_item,
    get_outlook_folder,
    newest_mail_items,
    resolve_smtp,
)


ENCODINGS = ["utf-8", "utf-16", "utf-16-le", "cp1252", "latin-1"]
DEFAULT_SENDERS = [
    "Morgan.Stanley.Swiss@morganstanley.com",
    "morgan",
    "morganstanley",
    "Morgan Stanley",
]

DEFAULT_MAILBOX = os.environ.get("PRICER_OUTLOOK_MAILBOX", "")
DEFAULT_FOLDER = os.environ.get("PRICER_OUTLOOK_FOLDER", "Inbox/Pricer")
DEFAULT_MAX_EMAILS = int(os.environ.get("PRICER_OUTLOOK_MAX", "5"))


def try_decode(path: pathlib.Path, encs=ENCODINGS):
    b = path.read_bytes()
    for e in encs:
        try:
            s = b.decode(e)
            return e, s
        except Exception:
            continue
    return None, None


def describe_obj(obj):
    print("RETURN TYPE:", type(obj))
    try:
        rep = repr(obj)
        print("repr (truncated):", rep[:2000])
    except Exception as e:
        print("repr failed:", e)

    if isinstance(obj, (list, tuple)):
        print(f"Sequence with {len(obj)} elements")
        for i, x in enumerate(obj):
            print(f" element[{i}] type={type(x)}")
            if isinstance(x, pd.DataFrame):
                print(f"  DataFrame shape={x.shape}")
                print(x.head(3).to_string())
            else:
                try:
                    print("  repr:", repr(x)[:1000])
                except Exception:
                    print("  could not repr element")
    else:
        if isinstance(obj, pd.DataFrame):
            print(f"DataFrame shape={obj.shape}")
            print("Columns:", list(obj.columns)[:20])
            print(obj.head(5).to_string())
        else:
            print("Not a DataFrame; see repr above for details")


def _parse_folder_arg(arg: str) -> list[str]:
    for sep in ("/", ">", "\\"):
        if sep in arg:
            return [p for p in arg.split(sep) if p]
    return [arg]


def _unique_ordered(items: Iterable[str]) -> Iterator[str]:
    seen: set[str] = set()
    for raw in items:
        item = (raw or "").strip()
        if not item or item.lower() in seen:
            continue
        seen.add(item.lower())
        yield item


def _init_com():
    try:
        import pythoncom  # type: ignore
    except Exception:
        return None
    try:
        pythoncom.CoInitialize()
    except Exception:
        return None
    return pythoncom


def _cleanup_com(pythoncom) -> None:
    if pythoncom is None:
        return
    try:
        pythoncom.CoUninitialize()
    except Exception:
        pass


def _fetch_outlook_messages(mailbox: str, folder_tokens: list[str], max_emails: int):
    pythoncom = _init_com()
    try:
        folder = get_outlook_folder(mailbox, folder_tokens)
        if folder is None:
            print(f"Could not resolve Outlook folder {folder_tokens} in mailbox {mailbox!r}.")
            return []
        msgs = newest_mail_items(folder, n=max_emails)
        if not msgs:
            print(f"No emails found in folder {folder_tokens}.")
            return []
        results = []
        for msg in msgs:
            try:
                html = clean_html_from_mail_item(msg)
            except Exception as exc:
                print(f"Skipping message due to HTML extraction error: {exc}")
                continue
            sender = resolve_smtp(msg) or ""
            subject = str(getattr(msg, "Subject", "") or "(no subject)")
            results.append({"html": html, "sender": sender, "subject": subject})
        return results
    finally:
        _cleanup_com(pythoncom)


def run_html_debug(html: str, senders: Iterable[str]):
    html = html or ""
    if not html.strip():
        print("HTML content is empty; nothing to parse.")
        return

    for sender in _unique_ordered(senders):
        issuer = detect_issuer_from_sender(sender)
        print(f"Sender={sender!r} -> detected issuer={issuer}")
        try:
            df_raw, extractor_issuer = extract_for_sender(html, sender)
        except Exception as e:
            print(" extract_for_sender raised:", repr(e))
            continue
        print(f" Extractor issuer guess={extractor_issuer!r}")
        if df_raw is None or (hasattr(df_raw, "empty") and df_raw.empty):
            print(" Extractor returned no rows.")
        else:
            describe_obj(df_raw)


def test_file(path_str: str):
    path = pathlib.Path(path_str)
    if not path.exists():
        print(f"File not found: {path}")
        return
    enc, html = try_decode(path)
    print(f"Decoded {path} using {enc}\n")

    if html is None:
        print("Could not decode file with tried encodings")
        return

    print(f"--- Testing file: {path} ---")
    run_html_debug(html, DEFAULT_SENDERS)


def test_outlook(mailbox: str, folder_str: str, max_emails: int):
    folder_tokens = _parse_folder_arg(folder_str)
    messages = _fetch_outlook_messages(mailbox, folder_tokens, max_emails=max_emails)
    if not messages:
        return
    for idx, msg in enumerate(messages, 1):
        sender = msg["sender"] or "(unknown)"
        subject = msg["subject"]
        print(f"\n=== Outlook message #{idx} | subject: {subject} | sender: {sender} ===")
        run_html_debug(msg["html"], [msg["sender"], *DEFAULT_SENDERS])


def main():
    argv = sys.argv[1:]
    if argv and argv[0].lower() == "outlook":
        mailbox = argv[1] if len(argv) > 1 else DEFAULT_MAILBOX
        folder = argv[2] if len(argv) > 2 else DEFAULT_FOLDER
        max_emails = int(argv[3]) if len(argv) > 3 else DEFAULT_MAX_EMAILS
        if not mailbox:
            print("Provide mailbox display name or set PRICER_OUTLOOK_MAILBOX.")
            return
        test_outlook(mailbox, folder, max_emails)
        return

    if DEFAULT_MAILBOX:
        print("Running Outlook mode via environment defaults...")
        test_outlook(DEFAULT_MAILBOX, DEFAULT_FOLDER, DEFAULT_MAX_EMAILS)
        return

    path = argv[0] if argv else MS_PATH
    print("Outlook mailbox not configured; falling back to file mode.")
    test_file(path)


if __name__ == "__main__":
    main()
