import io
import os
from typing import Optional, List

import pandas as pd
import streamlit as st
import requests

from app_core.extractors import (
    extract_for_sender,
    EXTRACTOR_BY_ISSUER,
    detect_issuer_from_sender,
)
from app_core.normalizers import normalize
from app_core.pipeline import run_on_html
from app_core.graph_auth import (
    load_config as graph_load_config,
    build_app as graph_build_app,
    build_auth_url as graph_build_auth_url,
    exchange_code_for_token as graph_exchange_code,
    get_me as graph_get_me,
    DEFAULT_SCOPES as GRAPH_SCOPES,
    get_serializable_cache as graph_get_cache,
    save_cache as graph_save_cache,
)
# Removed ticker lookup imports (CSV/API suggestions) per request

# Optional autocomplete component
try:
    from streamlit_searchbox import st_searchbox  # type: ignore
    _HAS_SEARCHBOX = True
except Exception:
    _HAS_SEARCHBOX = False


st.set_page_config(page_title="Email Pricer Parser", layout="wide")
st.title("Email Pricer Parser")

# Make OPENFIGI_API_KEY available from Streamlit secrets if provided
try:
    if "OPENFIGI_API_KEY" in st.secrets:
        os.environ["OPENFIGI_API_KEY"] = st.secrets["OPENFIGI_API_KEY"]
except Exception:
    pass

# Top-level tabs: keep existing parser flow and add an Email Pricing tab
tab_graph, tab_email_pricing = st.tabs(["Graph Parser", "Email Pricing"]) 


def _build_underlyings_key(row: pd.Series) -> str:
    parts: List[str] = []
    for i in range(1, 6):
        v = row.get(f"underlying_{i}")
        if pd.notna(v) and str(v).strip():
            parts.append(str(v).strip())
    return "+".join(parts) if parts else "NA"


def _make_key(df: pd.DataFrame, components: List[str]) -> pd.Series:
    cols = []
    for comp in components:
        if comp == "underlyings":
            cols.append(df.apply(_build_underlyings_key, axis=1))
        else:
            if comp in df.columns:
                cols.append(df[comp].astype(str).fillna("NA"))
            else:
                cols.append(pd.Series(["NA"] * len(df), index=df.index))
    if not cols:
        return pd.Series(["ALL"] * len(df), index=df.index)
    s = cols[0]
    for c in cols[1:]:
        s = s + "_" + c
    return s


# Early helpers to avoid NameError during initial UI render
def _abbr(issuer: Optional[str]) -> str:
    s = "NA" if issuer is None else str(issuer).strip()
    if not s:
        return "NA"
    try:
        return ABBR_MAP.get(s.lower(), s.upper())  # type: ignore[name-defined]
    except Exception:
        return s.upper()


def _bold_text(s: str) -> str:
    try:
        # If later redefined, Streamlit reruns will use the full version
        return str(s)
    except Exception:
        return str(s)

def _get_query_params() -> dict:
    try:
        # Streamlit >= 1.30
        return dict(st.query_params)
    except Exception:
        # Fallback
        try:
            return dict(st.experimental_get_query_params())
        except Exception:
            return {}


def _set_query_params(params: dict) -> None:
    try:
        st.query_params.clear()
        for k, v in (params or {}).items():
            st.query_params[k] = v
    except Exception:
        try:
            st.experimental_set_query_params(**(params or {}))
        except Exception:
            pass


# UI tweaks: smaller checkbox labels and prevent wrapping for one-line layout
st.markdown(
    """
    <style>
    div.stCheckbox > label, .stCheckbox label, label[for^="checkbox"] {
        font-size: 0.95rem !important;
        white-space: normal !important;
        line-height: 1.2rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -------------------------------
# Issuer table helpers (used early)
# -------------------------------

# Display ordering and ratings for issuer email table
ISSUER_DISPLAY_RATINGS = [
    ("Bank of America (Merrill Lynch)", "BOFA", "A- / A1"),
    ("Banque Cantonale Vaudoise", "BCV", "AA / -"),
    ("Barclays", "BARCLAYS", "A / A1"),
    ("Basler Kantonalbank", "BKB", "AA+ / -"),
    ("Banque Int. à Luxembourg", "BIL", "A- / A2"),
    ("BBVA", "BBVA", "A+ / A3"),
    ("BNP Paribas", "BNP", "A+ / Aa3"),
    ("Canadian Imp. Bank of Comm.", "CIBC", "A+ / Aa2"),
    ("Citi", "CITI", "A+ / A1"),
    ("Cornèr Bank", "CORNER", "BBB+"),
    ("Goldman Sachs", "GS", "A+ / A1"),
    ("HSBC", "HSBC", "A+ / A1"),
    ("JPMorgan", "JPM", "A+ / Aa2"),
    ("Julius Bär", "JB", "- / A3"),
    ("Leonteq", "LEONTEQ", "BBB"),
    ("Luzerner KB", "LUKB", "AA+ / -"),
    ("Marex", "MAREX", "BBB / -"),
    ("Morgan Stanley", "MS", "A- / A1"),
    ("Natixis", "NATIXIS", "A / A1"),
    ("Nomura Bank International", "NOMURA", "A- / -"),
    ("Raiffeisen", "RAIFFEISEN", "AA- / -"),
    ("Société Générale", "SOCGEN", "A / A1"),
    ("Swissquote", "SWISSQUOTE", "- / -"),
    ("UBS", "UBS", "A+ /Aa2"),
    ("Vontobel", "VONTOBEL", "- / A2"),
    ("Zürcher Kantonalbank", "ZKB", "AAA / Aaa"),
]

def _best_values_by_issuer(df: pd.DataFrame, column: str, asc: bool) -> dict:
    if column not in df.columns:
        return {}
    s = pd.to_numeric(df[column], errors="coerce")
    tmp = pd.concat([df["issuer"], s.rename("val")], axis=1).dropna(subset=["val"])
    if tmp.empty:
        return {}
    agg = tmp.groupby("issuer")["val"].agg("min" if asc else "max")
    return agg.to_dict()

def _format_var_value(val: Optional[float], var: str) -> str:
    if val is None or pd.isna(val):
        return "% p.a." if var == "coupon" else "%"
    try:
        v = float(val)
    except Exception:
        return "% p.a." if var == "coupon" else "%"
    if var == "coupon":
        return f"{v:.2f} % p.a."
    else:
        return f"{v:.2f} %"
def _build_issuer_table_df(df: pd.DataFrame, solve_var: str) -> pd.DataFrame:
    """Build issuer template table with dynamic sorting.
    - Always display Emittent, Rating, Coupon
    - Sort by: coupon desc; strike asc; barrier asc; default asc
    - Coupon text shows numeric value or 'OUT' if missing
    """
    sort_var = (solve_var or "").strip().lower()
    asc = False if sort_var == "coupon" else True
    metric = sort_var if sort_var else "coupon"
    sort_values = _best_values_by_issuer(df, metric, asc=asc)

    rows = []
    col_label = "Coupon" if metric == "coupon" else metric.title()
    for display, code, rating in ISSUER_DISPLAY_RATINGS:
        mval = sort_values.get(code)
        if metric in ("coupon", "strike", "barrier"):
            if mval is None or pd.isna(mval):
                cell_text = "OUT"
            else:
                if metric == "coupon":
                    cell_text = f"{float(mval):.2f} % p.a."
                else:
                    cell_text = f"{float(mval):.2f} %"
        else:
            cell_text = _format_var_value(mval, metric)
        rows.append({
            "Emittent": display,
            "Rating": rating,
            col_label: cell_text,
            "__sort__": (None if mval is None or pd.isna(mval) else float(mval)),
        })

    dfx = pd.DataFrame(rows)
    dfx = dfx.sort_values(by=["__sort__"], ascending=asc, na_position="last").drop(columns=["__sort__"])
    return dfx[["Emittent", "Rating", col_label]]

def _build_issuer_compare_table_df(
    df: pd.DataFrame,
    solve_var: str,
    versions: List[str],
    titles: List[str],
) -> pd.DataFrame:
    """Build an issuer table with multiple version columns (V1, V2, ...).
    Sorting is applied on the first version according to solve_var rule."""
    metric = (solve_var or "coupon").lower()
    asc = False if metric == "coupon" else True

    per_version_vals = []
    for v in versions:
        sub = df[df.get("_version_key") == v]
        vals = _best_values_by_issuer(sub, metric, asc=asc)
        per_version_vals.append(vals)

    rows = []
    for display, code, rating in ISSUER_DISPLAY_RATINGS:
        row = {"Emittent": display, "Rating": rating}
        # Ensure data exists; if not, stop safely
        try:
            if not isinstance(df_all, pd.DataFrame) or df_all.empty:
                st.stop()
        except Exception:
            pass
        sort_keys = []
        for idx, vals in enumerate(per_version_vals):
            mval = vals.get(code)
            if metric in ("coupon", "strike", "barrier"):
                if mval is None or pd.isna(mval):
                    txt = "OUT"
                    sort_keys.append(None)
                else:
                    num = float(mval)
                    if metric == "coupon":
                        txt = f"{num:.2f} % p.a."
                    else:
                        txt = f"{num:.2f} %"
                    sort_keys.append(num)
            else:
                txt = _format_var_value(mval, metric)
                try:
                    sort_keys.append(None if mval is None or pd.isna(mval) else float(mval))
                except Exception:
                    sort_keys.append(None)
            colname = f"{titles[idx]} {('Coupon' if metric=='coupon' else metric.title())}"
            row[colname] = txt
        for si, sval in enumerate(sort_keys):
            row[f"__sort_{si}"] = sval
        rows.append(row)

    dfx = pd.DataFrame(rows)
    sort_cols = [c for c in dfx.columns if c.startswith("__sort_")]
    if sort_cols:
        dfx = dfx.sort_values(by=sort_cols, ascending=[asc]*len(sort_cols), na_position="last")
        dfx = dfx.drop(columns=sort_cols)
    version_cols = [c for c in dfx.columns if c not in ("Emittent", "Rating")]
    return dfx[["Emittent", "Rating", *version_cols]]

# Display ordering and ratings for issuer email table (early definition)
 
# Visual style for solved fields (red highlight)
st.markdown(
    """
    <style>
    div.solved {
        background:#ffe6e6; border:1px solid #d9534f; color:#a94442;
        padding:8px 10px; border-radius:6px; margin-bottom:6px;
        font-size:0.9rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------
# Microsoft Graph helpers
# ---------------------------------

# Scopes for Graph delegated access. Some tenants/apps reject reserved scopes
# in the authorization request. Use only resource scopes here.
GRAPH_MAIL_SCOPES = ["User.Read", "Mail.Read"]


def _graph_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _graph_call(url: str, token: str, params: dict | None = None) -> dict:
    """Call Graph and parse JSON robustly.
    - Detects redirects/HTML and raises a clear error
    - Handles empty 200/204 without crashing
    """
    resp = requests.get(url, headers=_graph_headers(token), params=params or {}, timeout=15, allow_redirects=True)
    # Explicitly error on redirects to login/HTML pages that return 200 after redirect
    ct = (resp.headers.get("Content-Type") or "").lower()
    # Raise HTTP errors first
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        # Try to extract Graph error body if JSON
        try:
            data = resp.json()
            err = (data.get("error") or {}) if isinstance(data, dict) else {}
            msg = (err.get("message") or "").strip()
            code = err.get("code") or resp.status_code
            raise RuntimeError(f"Graph error {code}: {msg}") from e
        except Exception:
            # Non-JSON error body
            snippet = (resp.text or "").strip()[:200]
            raise RuntimeError(f"Graph HTTP {resp.status_code}. Body: {snippet}") from e

    # No content at all is acceptable for some endpoints
    text_body = (resp.text or "").strip()
    if not text_body:
        return {}
    # Content-type must be JSON
    if "application/json" not in ct and not (text_body.startswith("{") or text_body.startswith("[")):
        snippet = text_body[:200]
        raise RuntimeError(f"Graph returned non-JSON ({ct or 'unknown content-type'}). Body: {snippet}")
    # Parse JSON
    try:
        return resp.json()
    except Exception as e:
        snippet = text_body[:200]
        raise RuntimeError(f"Failed to parse Graph JSON. Body: {snippet}") from e


LOCALIZED_INBOX = {"inbox", "posteingang"}

def _graph_list_root_folders(token: str) -> list[dict]:
    items: list[dict] = []
    url = "https://graph.microsoft.com/v1.0/me/mailFolders?$top=200&$select=id,displayName,parentFolderId"
    while url:
        data = _graph_call(url, token)
        items.extend(data.get("value", []) or [])
        url = data.get("@odata.nextLink")
    return items

def _graph_list_children(token: str, parent_id: str) -> list[dict]:
    items: list[dict] = []
    url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{parent_id}/childFolders?$top=200&$select=id,displayName,parentFolderId"
    while url:
        data = _graph_call(url, token)
        items.extend(data.get("value", []) or [])
        url = data.get("@odata.nextLink")
    return items

def _graph_find_folder_by_path(token: str, folder_path: str) -> str | None:
    """Resolve a folder id by path like 'Inbox/Pricer' or 'Pricer'.
    - Case-insensitive match on displayName
    - Supports nested paths with '/'
    - Paginates through results
    - Fallback: when a single-part path isn't found at root, also search Inbox children
    - Supports localized Inbox names (e.g., 'Posteingang')
    """
    parts = [p.strip() for p in (folder_path or "Inbox").split("/") if p.strip()]
    if not parts:
        parts = ["Inbox"]

    # Initial listing context
    items: list[dict] = []
    idx = 0
    current: dict | None = None

    if parts and parts[0].lower() in LOCALIZED_INBOX:
        idx = 1
        items = _graph_list_children(token, "inbox")
    else:
        # Try root first
        items = _graph_list_root_folders(token)
        # If single segment not found at root, also try Inbox children as a convenience
        if len(parts) == 1 and not any(str(it.get("displayName", "")).lower() == parts[0].lower() for it in items):
            items = _graph_list_children(token, "inbox")

    # Traverse remaining parts
    for name in parts[idx:]:
        name_l = name.lower()
        match = next((it for it in items if str(it.get("displayName", "")).lower() == name_l), None)
        if match is None:
            return None
        current = match
        items = _graph_list_children(token, current.get("id"))

    return current.get("id") if current else ("inbox" if parts and parts[0].lower() in LOCALIZED_INBOX and idx == len(parts) else None)


def _graph_get_messages(token: str, folder_id: str, top: int = 40) -> list[dict]:
    params = {
        "$top": max(1, min(int(top or 40), 200)),
        "$orderby": "receivedDateTime desc",
        "$select": "id,receivedDateTime,from,sender,subject,body",
    }
    data = _graph_call(
        f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder_id}/messages",
        token,
        params=params,
    )
    return list(data.get("value", []))


def _graph_extract_html_and_sender(msg: dict) -> tuple[str, str]:
    b = (msg.get("body") or {})
    ctype = str(b.get("contentType") or "").lower()
    html = b.get("content") or ""
    if ctype != "html":
        # Fallback: wrap text as HTML
        html = f"<pre>{html}</pre>" if html else ""
    sender = (
        (((msg.get("from") or {}).get("emailAddress") or {}).get("address"))
        or (((msg.get("sender") or {}).get("emailAddress") or {}).get("address"))
        or ""
    )
    return html, sender


def _graph_handle_callback(conf: dict) -> None:
    """Handle OAuth redirect 'code' on any rerun, independent of where UI is rendered."""
    try:
        redirect_uri_local = conf.get("redirect_uri") or "http://localhost:8501"
        qp_local = _get_query_params()
        if "code" not in qp_local:
            return
        # Avoid re-exchanging if we already have a token
        if st.session_state.get("graph_token", {}).get("access_token"):
            return
        code_param = qp_local.get("code")
        if isinstance(code_param, (list, tuple)):
            code_param = code_param[0] if code_param else None
        if not code_param:
            return
        app_local = graph_build_app(conf)
        token = graph_exchange_code(app_local, code_param, GRAPH_MAIL_SCOPES, redirect_uri_local)
        if token and token.get("access_token"):
            st.session_state["graph_token"] = token
            try:
                me_local = graph_get_me(token.get("access_token"))
            except Exception:
                me_local = {}
            st.session_state["graph_me"] = me_local
            # Clean code from URL once processed
            cleaned = {k: v for k, v in qp_local.items() if k not in ("code", "state", "session_state")}
            _set_query_params(cleaned)
            st.toast("Microsoft Graph sign-in complete.")
        else:
            err = (token or {}).get("error_description") or (token or {}).get("error") or "Unknown token error"
            st.error(f"Graph token error: {err}")
    except Exception as e:
        st.error(f"Graph auth failed: {e}")


# Run Graph callback handler early so it works regardless of where the sign-in link is
_graph_conf_boot = graph_load_config()
_graph_handle_callback(_graph_conf_boot)

# ---------------------------------
# Email Pricing tab (input scaffold)
# ---------------------------------

with tab_graph:
    st.subheader("Graph Parser")
    conf = graph_load_config()
    redirect_uri = conf.get("redirect_uri") or "http://localhost:8501"
    # Persistent cache (optional)
    cache_path = os.path.join('.streamlit', 'msal_cache.json')
    cache = None
    try:
        cache = graph_get_cache(cache_path)
    except Exception:
        cache = None

    # Try silent token first
    token = None
    try:
        app = graph_build_app(conf, cache=cache)
        token = app.acquire_token_silent(["User.Read", "Mail.Read"], account=None)
        if token and token.get("access_token"):
            st.session_state["graph_token"] = token
            try:
                graph_save_cache(cache, cache_path)
            except Exception:
                pass
    except Exception:
        pass

    # Handle auth code callback
    try:
        qp = _get_query_params()
        if (not st.session_state.get("graph_token")) and ("code" in qp):
            code_param = qp.get("code")
            if isinstance(code_param, (list, tuple)):
                code_param = code_param[0] if code_param else None
            if code_param:
                app_cb = graph_build_app(conf, cache=cache)
                token = graph_exchange_code(app_cb, code_param, ["User.Read", "Mail.Read"], redirect_uri)
                if token and token.get("access_token"):
                    st.session_state["graph_token"] = token
                    try:
                        graph_save_cache(cache, cache_path)
                    except Exception:
                        pass
                    try:
                        me = graph_get_me(token.get("access_token"))
                        st.session_state["graph_me"] = me
                    except Exception:
                        pass
                    cleaned = {k: v for k, v in qp.items() if k not in ("code", "state", "session_state")}
                    _set_query_params(cleaned)
                    st.toast("Microsoft Graph sign-in complete.")
    except Exception as e:
        st.error(f"Graph auth failed: {e}")

    token = st.session_state.get("graph_token")
    if not (token and token.get("access_token")):
        st.info("Not signed in to Microsoft Graph.")
        try:
            app2 = graph_build_app(conf, cache=cache)
            auth_url = graph_build_auth_url(app2, ["User.Read", "Mail.Read"], redirect_uri)
            st.link_button("Sign in to Microsoft Graph", auth_url)
        except Exception as e:
            st.error(f"Failed to build auth URL: {e}")
        st.stop()

    me = st.session_state.get("graph_me") or {}
    st.caption(f"Signed in as: {me.get('displayName') or me.get('userPrincipalName') or 'user'}")

    # Prefill from URL query params if available (so users can bookmark it)
    try:
        qp = _get_query_params()
        qp_folder = qp.get("folder")
        if isinstance(qp_folder, (list, tuple)):
            qp_folder = qp_folder[0] if qp_folder else ""
        if qp_folder and not st.session_state.get("graph_folder_path"):
            st.session_state["graph_folder_path"] = str(qp_folder)
    except Exception:
        pass

    graph_folder_path = st.text_input(
        "Graph folder path",
        value=st.session_state.get("graph_folder_path", ""),
        help="Examples: 'Inbox/Pricer' or 'Projects/Pricer'. Leave blank for Inbox.",
        key="graph_folder_path",
    )

    # (Folder browse UI removed by request)
    graph_n = st.slider("Graph: newest N", 5, 200, 40, key="graph_n")

    if st.button("Start Parsing via Graph", key="start_graph"):
        access_token = st.session_state.get("graph_token", {}).get("access_token")
        folder_id = _graph_find_folder_by_path(access_token, graph_folder_path)
        if not folder_id:
            st.warning(f"Graph folder not found: {graph_folder_path}")
        else:
            # Persist chosen folder path in URL so colleagues don't need to retype
            try:
                _set_query_params({"folder": graph_folder_path})
            except Exception:
                pass
            msgs = _graph_get_messages(access_token, folder_id, top=int(graph_n))
            frames = []
            parsed_emails = 0
            debug_rows = []
            for msg in msgs:
                try:
                    html, sender = _graph_extract_html_and_sender(msg)
                    if not html:
                        continue
                    issuer_guess = detect_issuer_from_sender(sender or "")
                    raw_df = None
                    raw_issuer = None
                    extractor_error = None
                    try:
                        raw_df, raw_issuer = extract_for_sender(html, sender or "")
                    except Exception as exc:
                        extractor_error = repr(exc)
                    debug_entry = {
                        "Subject": msg.get("subject") or "(no subject)",
                        "Sender": sender or "(missing)",
                        "Detected issuer": issuer_guess or "(unmapped)",
                        "Extractor issuer": raw_issuer or "(none)",
                        "Extractor rows": 0 if raw_df is None else int(len(raw_df)),
                    }
                    if extractor_error:
                        debug_entry["Notes"] = f"extract error: {extractor_error[:120]}"
                    df = run_on_html(html, sender)
                    if df is not None and not df.empty:
                        frames.append(df)
                        parsed_emails += 1
                        debug_entry["Normalized rows"] = int(len(df))
                    else:
                        debug_entry["Normalized rows"] = 0
                    debug_rows.append(debug_entry)
                except Exception:
                    continue
            stats = {
                "retrieved_emails": len(msgs),
                "parsed_emails": parsed_emails,
                "parsed_rows": int(sum(len(f) for f in frames)) if frames else 0,
            }
            st.session_state["df_all"] = pd.concat(frames, ignore_index=True) if frames else None
            st.session_state["graph_debug_rows"] = debug_rows
            st.caption(
                f"Processed {stats['retrieved_emails']} Graph emails • Parsed {stats['parsed_emails']} • Rows {stats['parsed_rows']}"
            )
            if stats["parsed_emails"] > 0:
                st.success(f"Detected structured pricing tables in {stats['parsed_emails']} email(s).")
            else:
                st.warning("Fetched emails, but none contained detectable pricing tables.")

    df_all = st.session_state.get("df_all")

    if not isinstance(df_all, pd.DataFrame) or df_all.empty:
        st.info("Click 'Start Parsing via Graph' to load emails.")
    else:
        debug_rows = st.session_state.get("graph_debug_rows") or []

        ms_rows = 0
        if "issuer" in df_all.columns:
            ms_rows = int(df_all["issuer"].astype(str).str.lower().eq("ms").sum())
        if ms_rows > 0:
            st.success(f"Morgan Stanley detected in the latest batch • {ms_rows} parsed row(s).")
        elif "issuer" in df_all.columns:
            st.warning("No Morgan Stanley rows detected in the latest batch.")
        else:
            st.info("Parsed data does not include an 'issuer' column, unable to check for Morgan Stanley.")

        if debug_rows:
            with st.expander("Email detection debug", expanded=False):
                st.caption("Quick view of the last fetched messages and how the sender heuristics classified them.")
                st.dataframe(pd.DataFrame(debug_rows), use_container_width=True)

        # --- Version selection and issuer tables (restored) ---
        st.subheader("Select Versions")

        possible_vars = [c for c in ["coupon", "strike", "reoffer", "barrier"] if c in df_all.columns]
        if not possible_vars:
            st.warning("No standard metric columns (coupon, strike, reoffer, barrier) found in parsed data.")
            st.stop()
        solve_var = st.selectbox(
            "Select variable you are solving for:",
            options=possible_vars,
            index=0,
            key="graph_solve_var",
        )

        st.caption("Select Key Components:")
        label_map = {
            "underlyings": "Underlyings",
            "tenor": "Tenor",
            "barrier_type": "Barrier type",
            "barrier": "Barrier",
            "no_call_period": "No call period",
            "strike": "Strike",
            "coupon": "Coupon",
            "reoffer": "Reoffer",
        }
        help_map = {
            "underlyings": "Group by the underlying basket (codes 1..5)",
            "tenor": "Tenor in months",
            "barrier_type": "European/American",
            "barrier": "Barrier level (%)",
            "no_call_period": "Autocall from period (months)",
            "strike": "Put strike (%)",
            "coupon": "Coupon % p.a.",
            "reoffer": "Reoffer (%)",
        }
        comp_order = [
            "underlyings", "tenor", "barrier_type", "barrier",
            "no_call_period", "strike", "coupon", "reoffer",
        ]
        comp_default = {k: True for k in comp_order}
        comp_default["reoffer"] = False
        components, selected_labels = [], []
        per_row = 4
        for row_start in range(0, len(comp_order), per_row):
            row_items = comp_order[row_start:row_start+per_row]
            ccols = st.columns(len(row_items))
            for j, name in enumerate(row_items):
                label = label_map[name]
                disabled = (name == solve_var)
                checked = comp_default[name] and not disabled
                with ccols[j]:
                    val = st.checkbox(label, value=checked, disabled=disabled, help=help_map.get(name), key=f"graph_ck_{name}")
                if val:
                    components.append(name)
                    selected_labels.append(label)
        st.caption("Current key: " + (" + ".join(selected_labels) if selected_labels else "(none)"))

        def _get_version_labels_and_map(df: pd.DataFrame, components: list[str], solve_var: str):
            tmp = df.copy()
            tmp = tmp.assign(_version_key=_make_key(tmp, components))
            asc_local = False if solve_var == "coupon" else True
            grp = (
                tmp.groupby("_version_key")
                .agg(
                    rows=(solve_var, "size"),
                    issuers=("issuer", lambda s: len(set([str(x) for x in s if pd.notna(x)]))),
                    issuer_list=(
                        "issuer",
                        lambda s: sorted({ _abbr(x) for x in s if pd.notna(x) and str(x).strip() })
                    ),
                    metric=(solve_var, "mean"),
                )
                .reset_index()
                .sort_values(by=["metric"], ascending=asc_local)
            )
            recs = grp.to_dict("records")
            def _label(rec: dict) -> str:
                key = rec.get("_version_key", "")
                key_disp = _bold_text(str(key))
                cnt = int(rec.get("issuers", 0))
                ilist = list(rec.get("issuer_list", []))
                if len(ilist) > 10:
                    ilist = ilist[:10] + [f"+{len(ilist)-10}"]
                issuers_txt = ", ".join(ilist) if ilist else "-"
                return f"{key_disp} ({cnt} issuers: {issuers_txt})"
            labels = [_label(r) for r in recs]
            vmap = {lab: r.get("_version_key", "") for lab, r in zip(labels, recs)}
            return labels, vmap, recs

        version_labels, version_map, recs_internal = _get_version_labels_and_map(df_all, components, solve_var)

        mode = st.radio("Mode:", options=["Single version", "Compare versions"], index=0, key="graph_mode")
        if mode == "Single version":
            selected_label = st.selectbox("Choose version", options=(version_labels or ["(no versions)"]), key="graph_sel_version")
            selected_versions = [version_map[selected_label]] if version_labels else []
        else:
            selected_labels_multi = st.multiselect("Choose versions", options=version_labels, default=version_labels[:2], key="graph_multi_versions")
            selected_versions = [version_map[l] for l in selected_labels_multi]

        if st.button("Confirm Selection", key="graph_confirm"):
            df_view = df_all.copy().assign(_version_key=_make_key(df_all.copy(), components))
            out = df_view[df_view["_version_key"].isin(selected_versions)].copy() if selected_versions else df_view.copy()
            metric = (solve_var or "coupon").lower()
            asc = False if metric == "coupon" else True
            if solve_var in out.columns:
                out = out.sort_values(by=[solve_var], ascending=asc)
            if "issuer" in out.columns:
                out["issuer"] = out["issuer"].apply(_abbr)
            out_display = out.where(out.notna(), "NA")

            if mode == "Compare versions":
                titles = [f"V{i+1}" for i in range(len(selected_versions))]
                issuer_table_df = _build_issuer_compare_table_df(out, metric, selected_versions, titles)
            else:
                issuer_table_df = _build_issuer_table_df(out, metric)

            st.subheader("Issuer Table")
            st.dataframe(issuer_table_df, use_container_width=True)
            st.download_button(
                "Download Issuer Table CSV",
                data=issuer_table_df.to_csv(index=False).encode("utf-8"),
                file_name=f"issuer_table_{metric}.csv",
                mime="text/csv",
                key="graph_dl_issuer",
            )

            st.subheader("Selected Rows")
            st.dataframe(out_display, use_container_width=True)
            st.download_button(
                "Download Selected CSV",
                data=out_display.to_csv(index=False).encode("utf-8"),
                file_name="parsed_selection.csv",
                mime="text/csv",
                key="graph_dl_selected",
            )

        # Optional: preview the raw parsed data
        with st.expander("Parsed Data Preview", expanded=False):
            st.dataframe(df_all, use_container_width=True)
            st.download_button(
                "Download Parsed CSV",
                data=df_all.to_csv(index=False).encode("utf-8"),
                file_name="parsed_graph.csv",
                mime="text/csv",
                key="dl_graph_csv",
            )
with tab_email_pricing:
    st.subheader("Email Pricing")
    st.caption("Enter product details; we'll build a horizontal table email draft.")

    # Solve For outside the form so UI reacts instantly
    solve_for = st.selectbox(
        "Solve For",
        ["Coupon", "Strike", "Barrier", "Reoffer"],
        index=0,
        key="ep_solve_for",
    )

    with st.form("email_pricing_form"):
        # Use the value chosen above during this form render
        solve_for = st.session_state.get("ep_solve_for", "Coupon")

        # Product + key toggles at the top
        payoff_type = st.selectbox(
            "Payoff Type",
            [
                "Autocallable Phoenix",
                "Reverse Convertible",
                "Barrier Reverse Convertible",
                "Airbag",
                "Other",
            ],
            index=0,
        )
        autocallable = st.checkbox("Autocallable", value=True)

        # Pairs: Notional | Currency
        r1c1, r1c2 = st.columns(2)
        with r1c1:
            notional = st.number_input("Notional", min_value=0.0, value=100_000.0, step=1_000.0, format="%.0f")
        with r1c2:
            currency = st.selectbox("Currency", ["CHF", "EUR", "USD", "GBP"], index=0)

        # Pairs: Barrier Type | Barrier Level
        r2c1, r2c2 = st.columns(2)
        with r2c1:
            barrier_type = st.selectbox("Barrier Type", ["European", "American", "KI"], index=0)
        with r2c2:
            if solve_for == "Barrier":
                st.markdown("<div class='solved'>Barrier Level (%) — Solved (leave blank)</div>", unsafe_allow_html=True)
                barrier_level = st.session_state.get("barrier_level", 60.0)
            else:
                barrier_level = st.number_input("Barrier Level (%)", min_value=0.0, max_value=100.0, value=60.0, step=0.5)

        # Pairs: Tenor | Observation Frequency
        r3c1, r3c2 = st.columns(2)
        with r3c1:
            tenor_months = st.number_input("Tenor (months)", min_value=1, max_value=240, value=12, step=1)
        with r3c2:
            observation = st.selectbox("Observation Frequency", ["Monthly", "Quarterly", "Semi-Annual", "Annual"], index=0)

        # Additional toggles/values
        no_call_months = st.number_input("No-call period (months)", min_value=0, max_value=60, value=3, step=1)
        # Strike
        if solve_for == "Strike":
            st.markdown("<div class='solved'>Strike (%) — Solved (leave blank)</div>", unsafe_allow_html=True)
            strike = st.session_state.get("strike", 100.0)
        else:
            strike = st.number_input("Strike (%)", min_value=0.0, max_value=200.0, value=100.0, step=0.5)
        # Coupon
        if solve_for == "Coupon":
            st.markdown("<div class='solved'>Coupon (% p.a.) — Solved (leave blank)</div>", unsafe_allow_html=True)
            coupon_target = st.session_state.get("coupon_target", 12.0)
        else:
            coupon_target = st.number_input("Coupon (% p.a.)", min_value=0.0, max_value=100.0, value=12.0, step=0.1)
        # Reoffer
        if solve_for == "Reoffer":
            st.markdown("<div class='solved'>Reoffer (%) — Solved (leave blank)</div>", unsafe_allow_html=True)
            reoffer = st.session_state.get("reoffer", 100.0)
        else:
            reoffer = st.number_input("Reoffer (%)", min_value=0.0, max_value=105.0, value=100.0, step=0.1)

        st.caption("Underlyings (Bloomberg codes), one per column")
        ucols = st.columns(5)
        underlyings: List[str] = []
        for i in range(5):
            key_val = f"ep_under_{i+1}"
            with ucols[i]:
                val = st.text_input(f"Underlying {i+1}", key=key_val)
                if isinstance(val, str) and val.strip():
                    underlyings.append(val.strip())


        prepared = st.form_submit_button("Prepare Email Preview")

    if prepared:
        # Build a simple summary table for preview
        details = {
            "Payoff": payoff_type,
            "Currency": currency,
            "Notional": f"{notional:,.0f}",
            "Tenor (m)": int(tenor_months),
            "Obs. Freq": observation,
            "Autocallable": "Yes" if autocallable else "No",
            "No-call (m)": int(no_call_months),
            "Barrier Type": barrier_type,
            "Barrier (%)": f"{barrier_level:.2f}",
            "Strike (%)": f"{strike:.2f}",
            "Coupon (% p.a.)": f"{coupon_target:.2f}",
            "Reoffer (%)": f"{reoffer:.2f}",
            # Preferred Issuers removed per request
            "Underlyings": ", ".join(underlyings) if underlyings else "-",
            "Solve For": solve_for,
        }

        # Replace the chosen solve parameter with bold SOLVE in the preview/email
        solve_map = {
            "Coupon": "Coupon (% p.a.)",
            "Strike": "Strike (%)",
            "Barrier": "Barrier (%)",
            "Reoffer": "Reoffer (%)",
        }
        solve_key = solve_map.get(solve_for)
        if solve_key and solve_key in details:
            details[solve_key] = "<b>SOLVE</b>"

        df_preview = pd.DataFrame({"Field": list(details.keys()), "Value": list(details.values())})
        st.subheader("Email Preview")
        st.dataframe(df_preview, use_container_width=True)

        # Compose HTML body as a horizontal one-row table using your template headers
        col_order = [
            "Product",
            "Currency",
            "Size",
            "BBG Code 1",
            "BBG Code 2",
            "BBG Code 3",
            "BBG Code 4",
            "BBG Code 5",
            "Reoffer (%)",
            "Tenor (m)",
            "Frequency",
            "Autocall From Period",
            "Autocall Level (%)",
            "Memory Coupon",
            "Coupon Barrier (%)",
            "Coupon p.a. (%)",
            "Barrier Type",
            "KI Barrier (%)",
            "Put Strike (%)",
            "Gearing (%)",
            "Strike Date",
        ]

        # Map our form values to these headers; leave unknown fields blank
        # Underlyings -> BBG Code 1..5
        u_vals = underlyings + [""] * (5 - len(underlyings))
        # Derive simple defaults for fields we don't collect
        derived_memory_coupon = "Guaranteed" if autocallable else "None"
        derived_autocall_lvl = "100.00" if autocallable else ""
        derived_coupon_barrier = "0.00"  # not collected; set 0

        value_map = {
            "Product": payoff_type,
            "Currency": currency,
            "Size": f"{notional:,.0f}",
            "BBG Code 1": u_vals[0],
            "BBG Code 2": u_vals[1],
            "BBG Code 3": u_vals[2],
            "BBG Code 4": u_vals[3],
            "BBG Code 5": u_vals[4],
            "Reoffer (%)": f"{reoffer:.2f}",
            "Tenor (m)": int(tenor_months),
            "Frequency": observation,
            "Autocall From Period": int(no_call_months),
            "Autocall Level (%)": derived_autocall_lvl,
            "Memory Coupon": derived_memory_coupon,
            "Coupon Barrier (%)": derived_coupon_barrier,
            "Coupon p.a. (%)": f"{coupon_target:.2f}",
            "Barrier Type": barrier_type,
            "KI Barrier (%)": f"{barrier_level:.2f}",
            "Put Strike (%)": "",  # not collected
            "Gearing (%)": "",      # not collected
            "Strike Date": "",      # not collected
        }

        # If solving for a field, leave it blank in the output
        if solve_for == "Coupon":
            value_map["Coupon p.a. (%)"] = ""
        elif solve_for == "Strike":
            value_map["Put Strike (%)"] = ""
        elif solve_for == "Barrier":
            value_map["KI Barrier (%)"] = ""
        elif solve_for == "Reoffer":
            value_map["Reoffer (%)"] = ""

        # Horizontal table builder
        th_style = "padding:6px 10px;border:1px solid #ddd;background:#F2F2F2;white-space:nowrap;"
        td_base = "padding:6px 10px;border:1px solid #ddd;white-space:nowrap;"
        horiz_header = "".join([f"<th style='{th_style}'>{h}</th>" for h in col_order])
        horiz_cells = []
        for h in col_order:
            val = value_map.get(h, "")
            # Highlight solved field
            is_solve = (
                (solve_for == "Coupon" and h == "Coupon p.a. (%)") or
                (solve_for == "Strike" and h == "Put Strike (%)") or
                (solve_for == "Barrier" and h == "KI Barrier (%)") or
                (solve_for == "Reoffer" and h == "Reoffer (%)")
            )
            td_style = td_base + ("background-color:#fff3cd;" if is_solve else "")
            horiz_cells.append(f"<td style='{td_style}'>{val}</td>")
        horiz_row = "".join(horiz_cells)
        html_table_horizontal = f"""
        <div>
          <p>Please price the following:</p>
          <table style='border-collapse:collapse;font-family:Segoe UI, Arial, sans-serif;font-size:12.5px;'>
            <thead><tr>{horiz_header}</tr></thead>
            <tbody><tr>{horiz_row}</tr></tbody>
          </table>
        </div>
        """
        st.markdown(html_table_horizontal, unsafe_allow_html=True)
        # Persist for later button clicks across reruns
        st.session_state["pricing_email_html"] = html_table_horizontal
        st.session_state["pricing_email_subject"] = "Pricing Request"

    # Actions outside the form so buttons don’t depend on the form submit state
    st.divider()
    st.caption("Actions")
    colA, colB = st.columns([1,1])
    with colA:
        if st.button("Download Email HTML", key="ep_download_html"):
            html_body = st.session_state.get("pricing_email_html")
            if not html_body:
                st.warning("Prepare Email Preview first to generate the body.")
            else:
                st.download_button(
                    "Save HTML Body",
                    data=html_body.encode("utf-8"),
                    file_name="pricing_email.html",
                    mime="text/html",
                    key="ep_dl_inner",
                )
    with colB:
        st.caption("Copy/paste this HTML into your email client:")
        st.text_area("Email HTML", value=st.session_state.get("pricing_email_html", ""), height=180)


# Issuer abbreviation mapping for display and filtering
ABBR_MAP = {
    "goldman sachs": "GS", "gs": "GS",
    "bnpparibas": "BNP", "bnp": "BNP",
    "bank of america": "BOFA", "bofa": "BOFA",
    "citi": "CITI", "citigroup": "CITI",
    "natixis": "NATIXIS",
    "socgen": "SOCGEN", "société générale": "SOCGEN", "societe generale": "SOCGEN",
    "ms": "MS", "morgan stanley": "MS",
    "ubs": "UBS",
    "julius baer": "JB", "jb": "JB",
    "hsbc": "HSBC",
    "lukb": "LUKB",
    "marex": "MAREX",
    "bbva": "BBVA",
    "barclays": "BARCLAYS",
    "leonteq": "LEONTEQ",
    "swissquote": "SWISSQUOTE",
    "bkb": "BKB",
    "gs bank europe": "GS BANK EUROPE",
    "ltq": "LTQ",
    "cibc": "CIBC",
    # Additional banks for template mapping
    "banque cantonale vaudoise": "BCV",
    "bcv": "BCV",
    "basler kantonalbank": "BKB",
    "bkb": "BKB",
    "banque int. à luxembourg": "BIL",
    "banque internationale a luxembourg": "BIL",
    "bil": "BIL",
    "cornèr bank": "CORNER",
    "corner bank": "CORNER",
    "raiffeisen": "RAIFFEISEN",
    "vontobel": "VONTOBEL",
    "zkb": "ZKB",
    "zürcher kantonalbank": "ZKB",
    "nomura": "NOMURA",
    "nomura bank international": "NOMURA",
}


def _abbr(issuer: Optional[str]) -> str:
    if issuer is None:
        return "NA"
    s = str(issuer).strip()
    if not s:
        return "NA"
    return ABBR_MAP.get(s.lower(), s.upper())


# Render-alike bold for option text using Unicode Mathematical Bold characters
def _bold_text(s: str) -> str:
    if not isinstance(s, str):
        s = str(s)
    out = []
    for ch in s:
        o = ord(ch)
        # A-Z
        if 65 <= o <= 90:
            out.append(chr(0x1D400 + (o - 65)))
        # a-z
        elif 97 <= o <= 122:
            out.append(chr(0x1D41A + (o - 97)))
        # 0-9
        elif 48 <= o <= 57:
            out.append(chr(0x1D7CE + (o - 48)))
        else:
            out.append(ch)
    return "".join(out)

# (duplicate helpers removed; using early definitions above)

def _build_issuer_table_text_from_df(df: pd.DataFrame, solve_var: str, asc: bool) -> str:
    values = _best_values_by_issuer(df, solve_var, asc)
    header = "Emittent\tRating\t" + ("Coupon" if solve_var == "coupon" else solve_var.title())
    lines = [header]
    for display, code, rating in ISSUER_DISPLAY_RATINGS:
        val = values.get(code)
        lines.append(f"{display}\t{rating}\t{_format_var_value(val, solve_var)}")
    return "\n".join(lines)

def _build_filled_coupon_table_text(df: pd.DataFrame) -> str:
    values = _best_values_by_issuer(df, "coupon", asc=False)
    lines = ["Emittent\tRating\tCoupon"]
    for display, code, rating in ISSUER_DISPLAY_RATINGS:
        val = values.get(code)
        if val is not None and not pd.isna(val):
            lines.append(f"{display}\t{rating}\t{_format_var_value(val, 'coupon')}")
    return "\n".join(lines)

 


 
