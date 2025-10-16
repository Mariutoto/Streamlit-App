from __future__ import annotations

import importlib
from typing import Optional
import pandas as pd

from .cleanup import universal_cleanup
from .issuers import load_local_normalizer, load_legacy_normalizer


def _load_existing_normalizers_module():
    try:
        return importlib.import_module("Normalizers")
    except Exception:
        return None


_NORM_MOD = _load_existing_normalizers_module()


# Removed generic normalizer: enforce issuer-specific normalizers only


def normalize(df: pd.DataFrame, issuer: str | None) -> Optional[pd.DataFrame]:
    """Run issuer-specific normalizer then universal cleanup.

    Resolution order:
    1) app_core.issuers.<issuer>.normalize(df)
    2) Normalizers.normalize_<issuer>(df)  [legacy/toplevel]
    """
    issuer_key = (issuer or "").lower()
    if not issuer_key:
        return None

    # Prefer legacy Normalizers.py first (has richer mappings today)
    func = load_legacy_normalizer(issuer_key)
    if not func:
        # Fallback to local per-issuer module (customizable stubs)
        func = load_local_normalizer(issuer_key)
    if not func:
        return None

    try:
        cand = func(df)
    except Exception:
        return None

    dfn = cand.copy()
    if "issuer" not in dfn.columns:
        dfn["issuer"] = issuer if issuer is not None else pd.NA
    else:
        if issuer is not None:
            dfn["issuer"] = dfn["issuer"].fillna(issuer)

    return universal_cleanup(dfn, issuer_key)
