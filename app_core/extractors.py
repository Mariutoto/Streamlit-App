from __future__ import annotations

import importlib
from typing import Callable, Optional
import pandas as pd
from bs4 import BeautifulSoup

from .html_utils import normalize_html_rows, extract_best_table


def _load_existing_extractors_module():
    """Try to import user-provided Extractors.py (if present)."""
    try:
        mod = importlib.import_module("Extractors")
        # Patch missing helper, if needed
        if not hasattr(mod, "normalize_html_rows"):
            setattr(mod, "normalize_html_rows", normalize_html_rows)
        return mod
    except Exception:
        return None


_EXT_MOD = _load_existing_extractors_module()


def _call_or_generic(func_name: str, html: str) -> Optional[pd.DataFrame]:
    if _EXT_MOD and hasattr(_EXT_MOD, func_name):
        try:
            return getattr(_EXT_MOD, func_name)(html)
        except Exception:
            pass
    # Fallback generic
    return extract_best_table(html)


# Individual extractors (issuer names kept consistent with run_parser expectations)
def extract_natixis(html: str) -> Optional[pd.DataFrame]:
    return _call_or_generic("extract_natixis", html)


def extract_citi(html: str) -> Optional[pd.DataFrame]:
    return _call_or_generic("extract_citi", html)


def extract_bofa(html: str) -> Optional[pd.DataFrame]:
    return _call_or_generic("extract_bofa", html)


def extract_socgen(html: str) -> Optional[pd.DataFrame]:
    return _call_or_generic("extract_socgen", html)


def extract_gs(html: str) -> Optional[pd.DataFrame]:
    return _call_or_generic("extract_gs", html)


def extract_bnp(html: str) -> Optional[pd.DataFrame]:
    return _call_or_generic("extract_bnp", html)


def extract_lukb(html: str) -> Optional[pd.DataFrame]:
    return _call_or_generic("extract_lukb", html)


def extract_jb(html: str) -> Optional[pd.DataFrame]:
    return _call_or_generic("extract_jb", html)


def extract_hsbc(html: str) -> Optional[pd.DataFrame]:
    return _call_or_generic("extract_hsbc", html)


def extract_ms(html: str) -> Optional[pd.DataFrame]:
    return _call_or_generic("extract_ms", html)


def extract_ubs(html: str) -> Optional[pd.DataFrame]:
    return _call_or_generic("extract_ubs", html)


def extract_marex(html: str) -> Optional[pd.DataFrame]:
    return _call_or_generic("extract_marex", html)


def extract_bbva(html: str) -> Optional[pd.DataFrame]:
    return _call_or_generic("extract_bbva", html)


def extract_cibc(html: str) -> Optional[pd.DataFrame]:
    return _call_or_generic("extract_cibc", html)


def extract_barclays(html: str) -> Optional[pd.DataFrame]:
    return _call_or_generic("extract_barclays", html)


def extract_leonteq(html: str) -> Optional[pd.DataFrame]:
    return _call_or_generic("extract_leonteq", html)


def extract_swissquote(html: str) -> Optional[pd.DataFrame]:
    return _call_or_generic("extract_swissquote", html)


EXTRACTOR_BY_ISSUER = {
    "natixis": extract_natixis,
    "citi": extract_citi,
    "bofa": extract_bofa,
    "socgen": extract_socgen,
    "gs": extract_gs,
    "bnp": extract_bnp,
    "lukb": extract_lukb,
    "jb": extract_jb,
    "hsbc": extract_hsbc,
    "ms": extract_ms,
    "ubs": extract_ubs,
    "marex": extract_marex,
    "bbva": extract_bbva,
    "cibc": extract_cibc,
    "barclays": extract_barclays,
    "leonteq": extract_leonteq,
    "swissquote": extract_swissquote,
}


def extract_for_sender(html: str, sender: str) -> tuple[pd.DataFrame | None, str | None]:
    s = (sender or "").lower()
    # Heuristic mapping by domain substring
    mapping = [
        ("jpmorgan", "jpm"), ("jpm_autopricer", "jpm"), ("autopricer", "jpm"),
        ("natixis.com", "natixis"),
        ("citi.com", "citi"),
        ("bofa.com", "bofa"), ("bankofamerica.com", "bofa"),
        ("socgen.com", "socgen"), ("societegenerale.com", "socgen"), ("sgcib.com", "socgen"),
        ("gs.com", "gs"), ("gs-marquee-space", "gs"),
        ("bnpparibas.com", "bnp"), ("quotation.emea", "bnp"),
        ("lukb.ch", "lukb"),
        ("juliusbaer.com", "jb"), ("jbx.epricer@juliusbaer.com", "jb"),
        ("hsbc.com", "hsbc"), ("wmssp@hsbc.com", "hsbc"), ("hsbc.fr", "hsbc"),
        ("morganstanley.com", "ms"), ("morgan.stanley.swiss", "ms"),
        ("ubs.com", "ubs"), ("ol-rmp-marketaccess-ep@ubs.com", "ubs"),
        ("marex", "marex"), ("agile@marexfp.com", "marex"),
        ("bbva.com", "bbva"),
        ("cibc.com", "cibc"),
        ("barclays.com", "barclays"),
        ("leonteq.com", "leonteq"),
        ("swissquote.ch", "swissquote"), ("swissquote.com", "swissquote"),
    ]

    for needle, issuer in mapping:
        if needle in s:
            func = EXTRACTOR_BY_ISSUER.get(issuer)
            if func:
                return func(html), issuer
    # Unknown sender → best generic
    return extract_best_table(html), None

