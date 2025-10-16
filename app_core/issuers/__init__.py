"""
Issuer-specific normalizers live here.

Add a module per issuer (e.g., `citi.py`, `bofa.py`) exporting a
`normalize(df: pandas.DataFrame) -> pandas.DataFrame` function that maps
issuer-specific columns into the canonical schema. The pipeline will then
run the universal cleanup for final harmonization.

Discovery order when normalizing:
- app_core.issuers.<issuer>.normalize (preferred, local to this app)
- top-level Normalizers.normalize_<issuer> (backward compatibility)

Where <issuer> is the lowercase issuer key detected by extractors
(`app_core.extractors.EXTRACTOR_BY_ISSUER`).
"""

from __future__ import annotations

from importlib import import_module
from typing import Callable, Optional


def load_local_normalizer(issuer: str) -> Optional[Callable]:
    """Return `normalize(df)` from `app_core.issuers.<issuer>` if available."""
    mod_name = f"app_core.issuers.{issuer}"
    try:
        mod = import_module(mod_name)
    except Exception:
        return None
    func = getattr(mod, "normalize", None)
    return func if callable(func) else None


def load_legacy_normalizer(issuer: str) -> Optional[Callable]:
    """Return `normalize_<issuer>(df)` from top-level Normalizers.py if available."""
    try:
        legacy = import_module("Normalizers")
    except Exception:
        return None
    func = getattr(legacy, f"normalize_{issuer}", None)
    return func if callable(func) else None

