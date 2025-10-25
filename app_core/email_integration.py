from __future__ import annotations

from typing import List, Optional
from bs4 import BeautifulSoup
import time


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
    # Try to use EnsureDispatch for better COM marshaling
    try:
        app = win32.gencache.EnsureDispatch("Outlook.Application")  # type: ignore
    except Exception:
        app = win32.Dispatch("Outlook.Application")  # type: ignore

    # Helper: retry on RPC_E_CALL_REJECTED (Outlook busy / modal dialog)
    def _retry_call(fn, *args, **kwargs):
        last_err = None
        for i in range(8):
            try:
                return fn(*args, **kwargs)
            except Exception as e:  # pywintypes.com_error likely
                hr = getattr(e, "hresult", None)
                msg = str(e)
                # -2147418111 == 0x80010001 (RPC_E_CALL_REJECTED)
                if hr in (-2147418111, -2147023170) or "rejected" in msg.lower():
                    time.sleep(0.4 * (i + 1))
                    last_err = e
                    continue
                raise
        # Give up after retries
        raise last_err if last_err else RuntimeError("Outlook call failed after retries")

    ns = _retry_call(app.GetNamespace, "MAPI")

    # Resolve mailbox: allow display name or SMTP, case-insensitive contains
    store = None
    try:
        # Direct indexer by name sometimes works
        store = ns.Stores[mailbox]
    except Exception:
        # Fallback: scan stores by DisplayName
        try:
            count = ns.Stores.Count
        except Exception:
            count = 0
        mbox_l = (mailbox or "").lower()
        for i in range(1, count + 1):  # Outlook collections are 1-based
            try:
                st = ns.Stores.Item(i)
                name = str(getattr(st, "DisplayName", ""))
                if mbox_l and mbox_l in name.lower():
                    store = st
                    break
            except Exception:
                continue
    if store is None:
        return None

    root = _retry_call(store.GetRootFolder)
    folder = root
    for name in path:
        folder = _retry_call(folder.Folders.__getitem__, name)
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
