from __future__ import annotations

import importlib
from typing import Callable, Optional
import pandas as pd
from bs4 import BeautifulSoup

from .html_utils import normalize_html_rows


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


def _call_specific(func_name: str, html: str) -> Optional[pd.DataFrame]:
    """Call only the issuer-specific extractor if present; no generic fallback."""
    if _EXT_MOD and hasattr(_EXT_MOD, func_name):
        try:
            return getattr(_EXT_MOD, func_name)(html)
        except Exception:
            return None
    return None


# Individual extractors (issuer names kept consistent with run_parser expectations)
def extract_natixis(html: str) -> Optional[pd.DataFrame]:
    return _call_specific("extract_natixis", html)


def extract_citi(html: str) -> Optional[pd.DataFrame]:
    return _call_specific("extract_citi", html)


def extract_bofa(html: str) -> Optional[pd.DataFrame]:
    return _call_specific("extract_bofa", html)


def extract_socgen(html: str) -> Optional[pd.DataFrame]:
    return _call_specific("extract_socgen", html)


def extract_gs(html: str) -> Optional[pd.DataFrame]:
    return _call_specific("extract_gs", html)


def extract_bnp(html: str) -> Optional[pd.DataFrame]:
    return _call_specific("extract_bnp", html)


def extract_lukb(html: str) -> Optional[pd.DataFrame]:
    return _call_specific("extract_lukb", html)


def extract_jb(html: str) -> Optional[pd.DataFrame]:
    return _call_specific("extract_jb", html)


def extract_hsbc(html: str) -> Optional[pd.DataFrame]:
    return _call_specific("extract_hsbc", html)


def extract_ms(html: str) -> Optional[pd.DataFrame]:
    return _call_specific("extract_ms", html)


def extract_ubs(html: str) -> Optional[pd.DataFrame]:
    return _call_specific("extract_ubs", html)


def extract_marex(html: str) -> Optional[pd.DataFrame]:
    return _call_specific("extract_marex", html)


def extract_bbva(html: str) -> Optional[pd.DataFrame]:
    return _call_specific("extract_bbva", html)


def extract_cibc(html: str) -> Optional[pd.DataFrame]:
    return _call_specific("extract_cibc", html)


def extract_barclays(html: str) -> Optional[pd.DataFrame]:
    return _call_specific("extract_barclays", html)


def extract_leonteq(html: str) -> Optional[pd.DataFrame]:
    return _call_specific("extract_leonteq", html)


def extract_swissquote(html: str) -> Optional[pd.DataFrame]:
    return _call_specific("extract_swissquote", html)

def extract_nomura(html: str) -> Optional[pd.DataFrame]:
    return _call_specific("extract_nomura", html)

def extract_jpm(html: str) -> Optional[pd.DataFrame]:
    return _call_specific("extract_jpm", html)

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
    "nomura": extract_nomura,
    "jpm": extract_jpm,
}


SENDER_ISSUER_MAPPING: list[tuple[str, str]] = [
        ("jpmorgan", "jpm"), ("jpm_autopricer", "jpm"), ("autopricer", "jpm"),

            # accept short display names
            ("jpm", "jpm"), ("jpm markets", "jpm"), ("jpm.com", "jpm"), ("jpmorgan.com", "jpm"),
        ("natixis.com", "natixis"),
        ("citi.com", "citi"),
        ("bofa.com", "bofa"), ("bankofamerica.com", "bofa"),
        ("socgen.com", "socgen"), ("societegenerale.com", "socgen"), ("sgcib.com", "socgen"),
        ("gs.com", "gs"), ("gs-marquee-space", "gs"),
        ("bnpparibas.com", "bnp"), ("quotation.emea", "bnp"),
        ("lukb.ch", "lukb"), ("lukb", "lukb"),
        ("juliusbaer.com", "jb"), ("jbx.epricer@juliusbaer.com", "jb"),
        ("hsbc.com", "hsbc"), ("wmssp@hsbc.com", "hsbc"), ("hsbc.fr", "hsbc"),
        ("morganstanley.com", "ms"), ("morgan.stanley.swiss", "ms"), ("morgan stanley", "ms"), ("morganstanley", "ms"), ("morgan", "ms"),
        ("ubs.com", "ubs"), ("ol-rmp-marketaccess-ep@ubs.com", "ubs"), ("ol-ged-emailpricer@ubs.com", "ubs"),
    ("ubs", "ubs"),
        ("marex", "marex"), ("agile@marexfp.com", "marex"), ("marex.com", "marex"),
    ("bbva.com", "bbva"), ("alerts.bbva.com", "bbva"), ("bbvamarkets.com", "bbva"), ("bbvamarkets", "bbva"), ("bbva", "bbva"),
        ("cibc.com", "cibc"),
        ("barclays.com", "barclays"),
        ("leonteq.com", "leonteq"),
        ("swissquote.ch", "swissquote"), ("swissquote.com", "swissquote"),
        ("nomura.com", "nomura"), ("nomuraholdings.com", "nomura"),
    ]

def detect_issuer_from_sender(sender: str) -> Optional[str]:
    s = (sender or "").lower()
    # Try to extract domain from email-like strings first
    import re
    m = re.search(r"<([^>]+)>", s)
    addr = m.group(1) if m else s
    m2 = re.search(r"@([a-z0-9.\-]+)", addr)
    domain = m2.group(1) if m2 else None

    # Exact short aliases to avoid overly broad substring matches
    alias_exact = {
        "ms": "ms",
    }
    if s.strip() in alias_exact:
        return alias_exact[s.strip()]

    # Direct domain map
    domain_map = {
        "natixis.com": "natixis",
        "citi.com": "citi",
        "bofa.com": "bofa",
        "bankofamerica.com": "bofa",
        "socgen.com": "socgen",
        "societegenerale.com": "socgen",
        "sgcib.com": "socgen",
        "gs.com": "gs",
        "bnpparibas.com": "bnp",
        "lukb.ch": "lukb",
        "juliusbaer.com": "jb",
        "hsbc.com": "hsbc",
        "hsbc.fr": "hsbc",
        "morganstanley.com": "ms",
        "morgan.stanley.swiss": "ms",
        "ubs.com": "ubs",
        "marexfp.com": "marex",
        "marex.com": "marex",
        # BBVA variants seen in practice
        "bbva.com": "bbva",
        "alerts.bbva.com": "bbva",
        "bbvamarkets.com": "bbva",
        "bbvamarkets.es": "bbva",
        "bbva.es": "bbva",
        "cibc.com": "cibc",
        "barclays.com": "barclays",
        "leonteq.com": "leonteq",
        "swissquote.ch": "swissquote",
        "swissquote.com": "swissquote",
        "nomura.com": "nomura",
        "nomuraholdings.com": "nomura",
        # JPM variants
        "jpm.com": "jpm",
        "jpmorgan.com": "jpm",
    }
    if domain and domain in domain_map:
        return domain_map[domain]

    # Fallback to substring heuristics
    for needle, issuer in SENDER_ISSUER_MAPPING:
        if needle in s:
            return issuer
    return None


def extract_for_sender(html: str, sender: str) -> tuple[pd.DataFrame | None, str | None]:
    issuer = detect_issuer_from_sender(sender or "")
    if issuer:
        func = EXTRACTOR_BY_ISSUER.get(issuer)
        if func:
            return func(html), issuer
        return None, issuer
    # Unknown sender → do not fallback to generic
    return None, None
