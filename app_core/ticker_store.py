from __future__ import annotations

from functools import lru_cache
from typing import List, Dict, Optional
import pandas as pd


REQUIRED_COLUMNS = ["ticker", "name"]


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower().strip(): c for c in df.columns}
    def get(col: str) -> Optional[str]:
        for key in cols.keys():
            if key == col:
                return cols[key]
        return None

    out = pd.DataFrame()
    tcol = get("ticker") or get("symbol") or get("bbg_ticker") or get("bbg")
    ncol = get("name") or get("company") or get("security_name")
    ecol = get("exch") or get("exchange") or get("exch_code")
    bcol = get("bbg") or get("bloomberg") or get("composite")

    if tcol is None:
        raise ValueError("CSV must contain a ticker/symbol column")
    if ncol is None:
        ncol = tcol  # allow empty names

    out["ticker"] = df[tcol].astype(str).fillna("").str.strip()
    out["name"] = df[ncol].astype(str).fillna("").str.strip()
    out["exch"] = df[ecol].astype(str).fillna("").str.strip() if ecol else ""
    if bcol:
        out["bbg"] = df[bcol].astype(str).fillna("").str.strip()
    else:
        out["bbg"] = out.apply(
            lambda r: f"{r['ticker']} {r['exch']} Equity".strip() if r["exch"] else f"{r['ticker']} Equity",
            axis=1,
        )
    out = out.dropna(subset=["ticker"]).drop_duplicates(subset=["ticker", "exch"]) 
    return out


@lru_cache(maxsize=4)
def load_tickers_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    return _normalize_df(df)


def search_local_tickers(df: pd.DataFrame, query: str, limit: int = 10) -> List[Dict[str, str]]:
    q = (query or "").strip()
    if not q:
        return []
    ql = q.lower()
    # Prefix match on ticker, then substring on name
    pref = df[df["ticker"].str.lower().str.startswith(ql)]
    namehits = df[df["name"].str.lower().str.contains(ql, na=False)]
    combined = pd.concat([pref, namehits]).drop_duplicates().head(limit)
    out: List[Dict[str, str]] = []
    for _, r in combined.iterrows():
        out.append({
            "bbg": str(r["bbg"]),
            "ticker": str(r["ticker"]),
            "name": str(r["name"]),
            "exch": str(r.get("exch", "")),
            "source": "local",
        })
    return out

