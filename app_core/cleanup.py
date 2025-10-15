from __future__ import annotations

import numpy as np
import pandas as pd


REQUIRED_COLS = [
    "issuer", "product", "coupon", "currency", "tenor", "strike",
    "barrier", "reoffer", "underlying_1", "underlying_2", "underlying_3",
    "underlying_4", "underlying_5", "barrier_type",
    "autocall_barrier", "autocall_frequency", "no_call_period",
]


def universal_cleanup(df: pd.DataFrame, issuer: str | None = None) -> pd.DataFrame:
    df = df.copy()

    # Ensure required columns exist
    for col in REQUIRED_COLS:
        if col not in df.columns:
            df[col] = np.nan

    # Blank/NA normalization
    df = df.replace(r"^\s*$", np.nan, regex=True)
    df = df.replace({pd.NA: np.nan})

    # Numeric cleanup
    for col in ["coupon", "strike", "barrier", "reoffer", "autocall_barrier"]:
        df[col] = df[col].astype(str).str.replace("%", "", regex=False)
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Tenor to months
    def _parse_tenor_to_months(x):
        if pd.isna(x):
            return np.nan
        s = str(x).strip().lower()
        if s == "" or s in {"nan", "none"}:
            return np.nan
        if s.endswith("y"):
            try:
                return float(s[:-1].strip()) * 12
            except Exception:
                return np.nan
        if s.endswith("m"):
            s = s[:-1].strip()
        try:
            return float(s)
        except Exception:
            return np.nan

    df["tenor"] = pd.to_numeric(df["tenor"].apply(_parse_tenor_to_months), errors="coerce")

    # no_call_period cleanup (issuer-specific exceptions possible)
    if (issuer or "").lower() != "bofa":
        df["no_call_period"] = df["no_call_period"].astype(str).str.replace("m", "", case=False, regex=False)
        df["no_call_period"] = pd.to_numeric(df["no_call_period"], errors="coerce")

    # default no_call_period = 1 if 0 or NaN
    sel = df["no_call_period"].isna() | (df["no_call_period"] == 0)
    df.loc[sel, "no_call_period"] = 1

    # Normalize autocall_frequency
    freq_map = {
        "1": "Monthly", "3": "Quarterly", "6": "Semi-Annual", "12": "Annual",
        "quarterly": "Quarterly", "semi-annual": "Semi-Annual",
        "annual": "Annual", "monthly": "Monthly",
    }
    df["autocall_frequency"] = df["autocall_frequency"].astype(str).str.strip().map(lambda s: freq_map.get(s, s))

    # barrier_type normalization
    def _norm_barrier_type(x):
        if pd.isna(x):
            return np.nan
        s = str(x).strip().lower()
        alias = {
            "continuous": "american", "am": "american", "amer": "american",
            "american": "american", "eu": "european", "eur": "european",
            "european": "european",
        }
        s = alias.get(s, s)
        return s.title() if s in {"american", "european"} else np.nan

    df["barrier_type"] = df["barrier_type"].apply(_norm_barrier_type)

    # Clean underlyings safely
    def _clean_underlying(val):
        if pd.isna(val):
            return np.nan
        s = str(val).strip()
        if s.lower() in {"nan", "none", "", "<na>"}:
            return np.nan
        s = s.split(" ", 1)[0]
        s = s.split("_", 1)[0]
        s = s.split(".", 1)[0]
        s = s.replace(" Equity", "")
        return s if s else np.nan

    for col in ["underlying_1", "underlying_2", "underlying_3", "underlying_4", "underlying_5"]:
        if col in df.columns:
            df[col] = df[col].apply(_clean_underlying)

    # Universal NA homogenization
    na_like = ["", " ", "nan", "NaN", "none", "None", "NULL", "Null", "<NA>", pd.NA, np.nan, None]
    df = df.replace(na_like, np.nan)

    # Enforce types
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).replace("nan", np.nan)

    for col in ["coupon", "strike", "barrier", "reoffer", "autocall_barrier", "tenor", "no_call_period"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Enforce required order (subset safe)
    cols = [c for c in REQUIRED_COLS if c in df.columns]
    return df[cols]

