from __future__ import annotations

import importlib
from typing import Optional
import pandas as pd

from .cleanup import universal_cleanup


def _load_existing_normalizers_module():
    try:
        return importlib.import_module("Normalizers")
    except Exception:
        return None


_NORM_MOD = _load_existing_normalizers_module()


def _try_call_specific(norm_name: str, df: pd.DataFrame) -> Optional[pd.DataFrame]:
    if _NORM_MOD and hasattr(_NORM_MOD, norm_name):
        try:
            return getattr(_NORM_MOD, norm_name)(df)
        except Exception:
            return None
    return None


def _generic_normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Generic column harmonization
    rename_candidates = {
        "product": ["Product", "Product Name", "Ref"],
        "currency": ["Currency", "Ccy"],
        "tenor": ["Tenor", "Tenor (m)", "Tenor (M)", "Maturity (m)", "Maturity"],
        "strike": ["Strike", "Strike (%)", "Strike %"],
        "barrier": ["KI Barrier (%)", "Barrier (%)", "Barrier"],
        "barrier_type": ["Barrier Type", "KI Type"],
        "autocall_barrier": ["Autocall Barrier (%)", "Autocall Level (%)", "Early Termination Level (%)", "Trigger Level (%)"],
        "autocall_frequency": ["Autocall Frequency", "Frequency", "KO Frequency", "Early Termination Period"],
        "no_call_period": ["No Call Period", "Non Callable Period", "Non Autocallable Period", "Autocall From Period"],
        "coupon": ["Coupon p.a. (%)", "Coupon (%)", "Fixed Coupon p.a. (%)"],
        "reoffer": ["Reoffer (%)", "Upfront (%)", "Issue Price (%)"],
        "underlying_1": ["BBG Code 1", "Underlying 1"],
        "underlying_2": ["BBG Code 2", "Underlying 2"],
        "underlying_3": ["BBG Code 3", "Underlying 3"],
        "underlying_4": ["BBG Code 4", "Underlying 4"],
        "underlying_5": ["BBG Code 5", "Underlying 5"],
    }
    rename_map = {}
    for target, variants in rename_candidates.items():
        for v in variants:
            if v in df.columns:
                rename_map[v] = target
                break
    if rename_map:
        df = df.rename(columns=rename_map)
    # Ensure issuer column exists (filled later by caller)
    if "issuer" not in df.columns:
        df["issuer"] = pd.NA
    return df


def normalize(df: pd.DataFrame, issuer: str | None) -> pd.DataFrame:
    """Normalize and then apply universal cleanup."""
    issuer_key = (issuer or "").lower()

    # Try specific normalizer from user's module first
    if issuer_key:
        cand = _try_call_specific(f"normalize_{issuer_key}", df)
        if cand is not None:
            dfn = cand
        else:
            dfn = _generic_normalize(df)
    else:
        dfn = _generic_normalize(df)

    # Ensure issuer column is set; avoid fillna(None)
    if "issuer" not in dfn.columns:
        dfn["issuer"] = issuer if issuer is not None else pd.NA
    else:
        if issuer is not None:
            dfn["issuer"] = dfn["issuer"].fillna(issuer)

    return universal_cleanup(dfn, issuer_key)
