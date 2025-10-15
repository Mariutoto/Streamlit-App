from __future__ import annotations

from typing import Optional, List
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


def run_outlook(mailbox: str, folder_path: List[str], max_emails: int = 40) -> pd.DataFrame | None:
    folder = get_outlook_folder(mailbox, folder_path)
    if folder is None:
        return None
    msgs = newest_mail_items(folder, n=max_emails)
    if not msgs:
        return None
    frames = []
    for m in msgs:
        try:
            sender = resolve_smtp(m) or ""
            html = clean_html_from_mail_item(m)
        except Exception:
            continue
        df = run_on_html(html, sender)
        if df is not None and not df.empty:
            frames.append(df)
    if frames:
        return pd.concat(frames, ignore_index=True)
    return None

