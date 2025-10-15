from __future__ import annotations

from typing import List, Optional
from bs4 import BeautifulSoup


def _safe_import_outlook():
    try:
        import win32com.client as win32  # type: ignore
        return win32
    except Exception:
        return None


def get_outlook_folder(mailbox: str, path: List[str]):
    """
    Get an Outlook folder by mailbox and nested path, e.g. path=["Pricer"].
    Returns None if Outlook is not available.
    """
    win32 = _safe_import_outlook()
    if not win32:
        return None
    ns = win32.Dispatch("Outlook.Application").GetNamespace("MAPI")
    store = ns.Stores[mailbox]
    root = store.GetRootFolder()
    folder = root
    for name in path:
        folder = folder.Folders[name]
    return folder


def newest_mail_items(folder, n: int = 20):
    """Return newest n MailItems from an Outlook folder (or empty list)."""
    if folder is None:
        return []
    items = folder.Items
    items.Sort("[ReceivedTime]", True)
    out, itm = [], items.GetFirst()
    while itm and len(out) < n:
        try:
            if getattr(itm, "Class", None) == 43:  # MailItem
                out.append(itm)
        except Exception:
            pass
        itm = items.GetNext()
    return out


def clean_html_from_mail_item(msg) -> str:
    html = getattr(msg, "HTMLBody", "") or ""
    soup = BeautifulSoup(html, "html.parser")
    for q in soup.select("blockquote"):
        q.decompose()
    return str(soup)


def resolve_smtp(msg) -> Optional[str]:
    """Best-effort sender email address resolution for Outlook MailItem."""
    try:
        pa = msg.PropertyAccessor
        smtp = pa.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x39FE001E")
        if smtp:
            return str(smtp).lower()
    except Exception:
        pass
    try:
        if msg.Sender is not None:
            if hasattr(msg.Sender, "Address"):
                return str(msg.Sender.Address).lower()
            if hasattr(msg.Sender, "Name"):
                return str(msg.Sender.Name).lower()
    except Exception:
        pass
    try:
        return (msg.SenderEmailAddress or "").lower()
    except Exception:
        return None

