from __future__ import annotations

import os
import json
from typing import List, Dict

import requests


def _openfigi_search(query: str, limit: int = 10) -> List[Dict[str, str]]:
    api_key = os.getenv("9d88f101-ee95-42fe-8604-4b2340a2777a")
    if not api_key:
        return []
    url = "https://api.openfigi.com/v3/search"
    headers = {"Content-Type": "application/json", "X-OPENFIGI-APIKEY": api_key}
    payload = {"query": query, "exchCode": None}
    try:
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=8)
        if r.status_code != 200:
            return []
        data = r.json() or {}
        results = data.get("data") or []
        out: List[Dict[str, str]] = []
        for item in results:
            # Bloomberg-style composite ticker: TICKER + country/exch + asset class
            ticker = (item.get("ticker") or "").strip()
            exch = (item.get("exchCode") or "").strip()
            name = (item.get("name") or "").strip()
            # Market sector often like 'Equity', ensure proper suffix
            sector = (item.get("marketSector") or "").strip() or "Equity"
            if not ticker:
                continue
            bbg = f"{ticker} {exch} {sector}".strip()
            out.append({
                "bbg": bbg,
                "ticker": ticker,
                "name": name,
                "exch": exch,
                "source": "openfigi",
            })
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


def _yahoo_search(query: str, limit: int = 10) -> List[Dict[str, str]]:
    # Public Yahoo Finance search endpoint
    url = "https://query1.finance.yahoo.com/v1/finance/search"
    params = {"q": query, "quotesCount": limit, "newsCount": 0, "listsCount": 0}
    try:
        r = requests.get(url, params=params, timeout=8)
        if r.status_code != 200:
            return []
        data = r.json() or {}
        quotes = data.get("quotes") or []
        out: List[Dict[str, str]] = []
        for q in quotes:
            symbol = (q.get("symbol") or "").strip()
            shortname = (q.get("shortname") or q.get("longname") or "").strip()
            exch_disp = (q.get("exchDisp") or q.get("exchange") or "").strip()
            # Approximate Bloomberg composite format: SYMBOL CCY/EXCH Equity (best-effort)
            # We keep the value as SYMBOL for safety and display a best-effort BBG-like label.
            bbg_like = f"{symbol} {exch_disp} Equity".strip()
            out.append({
                "bbg": bbg_like,
                "ticker": symbol,
                "name": shortname,
                "exch": exch_disp,
                "source": "yahoo",
            })
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


def suggest_tickers(query: str, limit: int = 10) -> List[Dict[str, str]]:
    """Return a list of suggestions with keys: bbg, ticker, name, exch, source.
    Priority: OpenFIGI (requires OPENFIGI_API_KEY) -> Yahoo fallback.
    """
    query = (query or "").strip()
    if not query:
        return []
    suggestions = _openfigi_search(query, limit=limit)
    if suggestions:
        return suggestions
    return _yahoo_search(query, limit=limit)

