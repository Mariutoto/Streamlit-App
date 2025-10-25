from __future__ import annotations

from typing import Optional, List, Tuple, Dict
import pandas as pd

from .extractors import extract_for_sender
from .normalizers import normalize
from .email_integration import (
    get_outlook_folder,
    newest_mail_items,
    clean_html_from_mail_item,
    resolve_smtp,
)


def run_on_html(html: str, sender: Optional[str] = None, issuer_override: Optional[str] = None) -> pd.DataFrame | None:
    df_raw, detected_issuer = extract_for_sender(html, sender or "")
    issuer = issuer_override or detected_issuer
    if df_raw is None or df_raw.empty:
        return None
    return normalize(df_raw, issuer)


def run_outlook(
    mailbox: str,
    folder_path: List[str],
    max_emails: int = 40,
) -> Tuple[Optional[pd.DataFrame], Dict[str, int]]:
    # Ensure COM is initialized for this thread during Outlook access
    try:
        import pythoncom  # type: ignore
        pythoncom.CoInitialize()
    except Exception:
        pythoncom = None  # best-effort; continue and let calls raise if needed

    try:
        folder = get_outlook_folder(mailbox, folder_path)
        if folder is None:
            return None, {"retrieved_emails": 0, "parsed_emails": 0, "parsed_rows": 0}
        msgs = newest_mail_items(folder, n=max_emails)
        if not msgs:
            return None, {"retrieved_emails": 0, "parsed_emails": 0, "parsed_rows": 0}
        frames = []
        parsed_emails = 0
        for m in msgs:
            try:
                sender = resolve_smtp(m) or ""
                html = clean_html_from_mail_item(m)
            except Exception:
                continue
            df = run_on_html(html, sender)
            if df is not None and not df.empty:
                frames.append(df)
                parsed_emails += 1
        stats = {
            "retrieved_emails": len(msgs),
            "parsed_emails": parsed_emails,
            "parsed_rows": int(sum(len(f) for f in frames)) if frames else 0,
        }
        if frames:
            return pd.concat(frames, ignore_index=True), stats
        return None, stats
    finally:
        try:
            if pythoncom is not None:
                pythoncom.CoUninitialize()
        except Exception:
            pass
