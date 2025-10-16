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


# Removed generic normalizer: enforce issuer-specific normalizers only


def normalize(df: pd.DataFrame, issuer: str | None) -> Optional[pd.DataFrame]:
    """Apply only issuer-specific normalizers followed by universal cleanup; no generic fallback."""
    issuer_key = (issuer or "").lower()

    if not issuer_key:
        return None

    cand = _try_call_specific(f"normalize_{issuer_key}", df)
    if cand is None:
        return None

    dfn = cand.copy()
    if "issuer" not in dfn.columns:
        dfn["issuer"] = issuer if issuer is not None else pd.NA
    else:
        if issuer is not None:
            dfn["issuer"] = dfn["issuer"].fillna(issuer)

    return universal_cleanup(dfn, issuer_key)
