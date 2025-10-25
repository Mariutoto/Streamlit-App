from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _extract_headers(tr) -> List[str]:
    headers: List[str] = []
    for td in tr.find_all(["td", "th"], recursive=False):
        headers.append(_norm(td.get_text(" ", strip=True)))
    return headers


def _format_val(val: str | float | int | None) -> str:
    if val is None:
        return ""
    return str(val)


def render_pricing_email_from_draft(
    draft_html_path: str,
    details: Dict[str, str],
    client_name: Optional[str] = None,
    comments: Optional[str] = None,
) -> str:
    """
    Load a Word/Outlook-style HTML draft and replace the first data row of the
    main table using column headers. Falls back gracefully if headers differ.
    """
    with open(draft_html_path, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()

    soup = BeautifulSoup(raw, "html.parser")

    # Attempt to update greeting
    if client_name:
        # Replace first occurrence of a greeting line if present
        p = soup.find("p", string=lambda x: isinstance(x, str) and _norm("hi ") in _norm(x))
        # If no typical greeting paragraph found, we leave existing text as-is

    # Find the first significant table and update values by header name
    tbl = soup.find("table")
    if tbl:
        rows = tbl.find_all("tr", recursive=False)
        if len(rows) >= 2:
            header_tr = rows[0]
            data_tr = rows[1]
            headers = _extract_headers(header_tr)
            data_tds = data_tr.find_all(["td", "th"], recursive=False)

            # Mapping from our details keys to expected header names
            want_map = {
                "payoff": ["product", "payoff", "product type"],
                "currency": ["currency"],
                "notional": ["size", "notional", "amount"],
                "tenor (m)": ["tenor", "maturity", "tenor (m)"],
                "obs. freq": ["observation", "obs. freq", "observation frequency"],
                "autocallable": ["autocall", "autocallable"],
                "no-call (m)": ["no call", "nc", "no-call"],
                "barrier type": ["barrier type", "type"],
                "barrier (%)": ["barrier", "barrier (%)"],
                "strike (%)": ["strike", "strike (%)"],
                "coupon (% p.a.)": ["coupon", "coupon (% p.a.)"],
                "reoffer (%)": ["reoffer", "reoffer (%)"],
                "underlyings": ["underlyings", "underlying", "basket"],
                "preferred issuers": ["issuer", "preferred issuers", "issuers"],
            }

            # Reverse index from header text -> col index
            header_index: Dict[str, int] = {h: i for i, h in enumerate(headers)}

            for key, aliases in want_map.items():
                val = details.get(key) or details.get(key.title()) or details.get(key.capitalize())
                if not val:
                    continue
                # find column by alias
                idx: Optional[int] = None
                for a in aliases:
                    if a in header_index:
                        idx = header_index[a]
                        break
                if idx is None:
                    # try contains match
                    for h, i in header_index.items():
                        for a in aliases:
                            if a in h:
                                idx = i
                                break
                        if idx is not None:
                            break
                if idx is not None and idx < len(data_tds):
                    data_tds[idx].string = _format_val(val)

    # Optionally append comments after table
    if comments:
        # Insert a comment paragraph after the table, if found
        if tbl and tbl.parent:
            new_p = soup.new_tag("p")
            new_p.string = comments
            tbl.parent.insert(tbl.parent.contents.index(tbl) + 1, new_p)

    # Prefer to return only the BODY inner HTML for Outlook.HTMLBody
    if soup.body is not None:
        return soup.body.decode_contents()
    # Fallbacks: return table HTML or the whole soup as string
    if tbl is not None:
        return str(tbl)
    return str(soup)
