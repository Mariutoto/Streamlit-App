import io
import os
from typing import Optional, List

import pandas as pd
import streamlit as st
import requests

from app_core.extractors import (
    extract_for_sender,
    EXTRACTOR_BY_ISSUER,
)
from app_core.normalizers import normalize
from app_core.email_integration import (
    get_outlook_folder,
    newest_mail_items,
    clean_html_from_mail_item,
    resolve_smtp,
)
from app_core.pipeline import run_on_html, run_outlook
from app_core.graph_auth import (
    load_config as graph_load_config,
    build_app as graph_build_app,
    build_auth_url as graph_build_auth_url,
    exchange_code_for_token as graph_exchange_code,
    get_me as graph_get_me,
    DEFAULT_SCOPES as GRAPH_SCOPES,
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
tab_parser, tab_graph, tab_email_pricing, tab_outlook = st.tabs(["Parser", "Graph Parser", "Email Pricing", "Outlook Test"]) 
with tab_parser:
    st.caption("Parser UI is currently rendered below and will be moved into this tab in a later refactor.")


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
    r = requests.get(url, headers=_graph_headers(token), params=params or {}, timeout=15)
    r.raise_for_status()
    return r.json()


def _graph_find_folder_by_path(token: str, folder_path: str) -> str | None:
    """Return folder id for a displayName path like 'Inbox/Pricer'. Case-insensitive."""
    parts = [p.strip() for p in (folder_path or "Inbox").split("/") if p.strip()]
    if not parts:
        parts = ["Inbox"]
    # Start from root mail folders
    data = _graph_call("https://graph.microsoft.com/v1.0/me/mailFolders", token, params={"$top": 200})
    current = None
    items = data.get("value", [])
    for name in parts:
        name_l = name.lower()
        match = None
        for it in items:
            if str(it.get("displayName", "")).lower() == name_l:
                match = it
                break
        if match is None:
            return None
        current = match
        # Load children for next iteration
        resp = _graph_call(
            f"https://graph.microsoft.com/v1.0/me/mailFolders/{current.get('id')}/childFolders",
            token,
            params={"$top": 200},
        )
        items = resp.get("value", [])
    return current.get("id") if current else None


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
        if st.button("Open Draft in Outlook", key="ep_open_outlook"):
            try:
                html_body = st.session_state.get("pricing_email_html")
                subject = st.session_state.get("pricing_email_subject", "Pricing Request")
                if not html_body:
                    st.warning("Prepare Email Preview first to generate the body.")
                else:
                    import pythoncom  # type: ignore
                    pythoncom.CoInitialize()
                    import win32com.client as win32  # type: ignore
                    outlook = win32.Dispatch("Outlook.Application")
                    mail = outlook.CreateItem(0)  # olMailItem
                    mail.Subject = subject
                    try:
                        mail.BodyFormat = 2  # olFormatHTML
                    except Exception:
                        pass
                    mail.HTMLBody = html_body + getattr(mail, "HTMLBody", "")
                    mail.Display()
                    st.success("Outlook draft opened.")
            except Exception as e:
                st.exception(e)
            finally:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
    with colB:
        if st.button("Open Blank Outlook Email", key="ep_test_outlook_inline"):
            try:
                import pythoncom  # type: ignore
                pythoncom.CoInitialize()
                import win32com.client as win32  # type: ignore
                outlook = win32.Dispatch("Outlook.Application")
                mail = outlook.CreateItem(0)
                mail.Subject = ""
                mail.Body = ""
                mail.Display()
                st.success("Blank Outlook email opened.")
            except Exception as e:
                st.exception(e)
            finally:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass


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

def _build_issuer_table_df(df: pd.DataFrame, solve_var: str) -> pd.DataFrame:
    """Build issuer template table with dynamic sorting.
    - Always display Emittent, Rating, Coupon
    - Sort by: coupon desc; strike asc; barrier asc; default asc
    - Coupon text shows numeric value or 'OUT' if missing
    """
    # Sorting rule
    sort_var = (solve_var or "").strip().lower()
    asc = True
    if sort_var == "coupon":
        asc = False
    elif sort_var in ("strike", "barrier"):
        asc = True
    else:
        asc = True

    # Values for sorting and for coupon display
    metric = sort_var if sort_var else "coupon"
    sort_values = _best_values_by_issuer(df, metric, asc=asc)

    rows = []
    col_label = "Coupon" if metric == "coupon" else metric.title()
    for display, code, rating in ISSUER_DISPLAY_RATINGS:
        mval = sort_values.get(code)
        if metric in ("coupon", "strike", "barrier"):
            # Show OUT when missing for coupon/strike/barrier
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

    # Prepare per-version value dicts
    per_version_vals = []
    for v in versions:
        sub = df[df.get("_version_key") == v]
        vals = _best_values_by_issuer(sub, metric, asc=asc)
        per_version_vals.append(vals)

    rows = []
    # Build rows per issuer
    for display, code, rating in ISSUER_DISPLAY_RATINGS:
        row = {"Emittent": display, "Rating": rating}
        # Collect numeric sort keys per version
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
        # Store sort keys for multi-key sort (V1, then V2, ...)
        for si, sval in enumerate(sort_keys):
            row[f"__sort_{si}"] = sval
        rows.append(row)

    dfx = pd.DataFrame(rows)
    sort_cols = [c for c in dfx.columns if c.startswith("__sort_")]
    if sort_cols:
        dfx = dfx.sort_values(by=sort_cols, ascending=[asc]*len(sort_cols), na_position="last")
        dfx = dfx.drop(columns=sort_cols)
    # Order columns: Emittent, Rating, then version columns
    version_cols = [c for c in dfx.columns if c not in ("Emittent", "Rating")]
    return dfx[["Emittent", "Rating", *version_cols]]


with st.sidebar:
    st.header("Outlook Folder")
    st.info("Requires Outlook/pywin32 on this machine.")
    mailbox = st.text_input("Mailbox SMTP or display name", value="boulbenmeyer@calebocapital.ch")
    # Default to just 'Pricer' to match the user's setup. The Outlook
    # integration will also try Inbox/ as a fallback automatically.
    folder_path = st.text_input("Folder path (use '/' for nesting)", value="Pricer")
    n = st.slider("Fetch newest N emails", 5, 200, 40)

    issuer_keys = [k for k in EXTRACTOR_BY_ISSUER.keys()]
    issuer_override = st.selectbox(
        "Issuer override (optional)",
        [""] + issuer_keys,
        index=0,
        help="If set, forces this issuer's extractor/normalizer",
    )
    issuer_override = issuer_override or None

    st.divider()
    st.header("Microsoft Graph")
    st.caption("Sign in and load emails via Graph (cloud)")
    conf = graph_load_config()
    redirect_uri = conf.get("redirect_uri") or "http://localhost:8501"
    # Quick config diagnostics (no secret value shown)
    _cid = conf.get("client_id") or ""
    _tid = conf.get("tenant_id") or ""
    _csec = bool(conf.get("client_secret"))
    if not _cid:
        st.warning("AZURE_CLIENT_ID is not set. Create .streamlit/secrets.toml with your app values.")
    if not _tid:
        st.info("Using default tenant 'common'. Set AZURE_TENANT_ID to restrict to your tenant.")
    st.caption(
        "Config status → "
        + ("client_id: MISSING • " if not _cid else "client_id: OK • ")
        + ("tenant_id: " + (_tid[:6] + "…" if _tid else "common"))
        + " • client_secret: " + ("OK" if _csec else "MISSING")
    )
    # Preflight: block Graph sign-in if required config is missing
    _graph_ready = True
    _missing = []
    if not _cid:
        _missing.append("AZURE_CLIENT_ID")
    if not (conf.get("redirect_uri") or "").strip():
        _missing.append("AZURE_REDIRECT_URI")
    if _missing:
        _graph_ready = False
        st.error(
            "Microsoft Graph is not configured: missing "
            + ", ".join(_missing)
            + ". Update .streamlit/secrets.toml and restart the app."
        )
    # Exchange authorization code if present
    qp = _get_query_params()
    _has_token = bool(st.session_state.get("graph_token", {}).get("access_token"))
    try:
        if _graph_ready and (not _has_token) and ("code" in qp):
            app = graph_build_app(conf)
            code_param = qp.get("code")
            if isinstance(code_param, (list, tuple)):
                code_param = code_param[0] if code_param else None
            if code_param:
                token = graph_exchange_code(app, code_param, GRAPH_MAIL_SCOPES, redirect_uri)
                if token and token.get("access_token"):
                    st.session_state["graph_token"] = token
                    # Optional: fetch profile to show signed-in user
                    try:
                        me = graph_get_me(token.get("access_token"))
                    except Exception:
                        me = {}
                    st.session_state["graph_me"] = me
                    # Clean code from URL
                    cleaned = {k: v for k, v in qp.items() if k not in ("code", "state", "session_state")}
                    _set_query_params(cleaned)
                    st.success("Microsoft Graph sign-in complete.")
                else:
                    err = (token or {}).get("error_description") or (token or {}).get("error") or "Unknown token error"
                    st.error(f"Graph token error: {err}")
    except Exception as e:
        st.error(f"Graph auth failed: {e}")

    token = st.session_state.get("graph_token")
    if token and token.get("access_token"):
        me = st.session_state.get("graph_me") or {}
        disp = me.get("displayName") or me.get("userPrincipalName") or "Signed in"
        st.success(f"{disp}")
        graph_folder_path = st.text_input("Graph folder path", value="Inbox/Pricer", key="graph_folder_path")
        graph_n = st.slider("Graph: newest N", 5, 200, 40, key="graph_n_slider")
    else:
        st.info("Not signed in to Microsoft Graph.")
        if _graph_ready:
            try:
                app = graph_build_app(conf)
                auth_url = graph_build_auth_url(app, GRAPH_MAIL_SCOPES, redirect_uri)
                st.markdown(f"[Sign in with Microsoft]({auth_url})")
                st.caption(f"Redirect URI: {redirect_uri}")
            except Exception as e:
                st.error(f"Configure Azure app in .streamlit/secrets.toml: {e}")

    # Diagnostics to help when no data is parsed
    with st.expander("Diagnostics: Outlook folder/parse", expanded=False):
        st.caption("Helps verify folder selection and sender/issuer mapping.")
        peek_n = st.number_input("Peek newest N", min_value=1, max_value=50, value=5, step=1, key="peek_n")
        if st.button("Peek selected Outlook folder", key="peek_btn"):
            try:
                folder = get_outlook_folder(mailbox, [p for p in (folder_path or '').split('/') if p])
                if folder is None:
                    st.error("Folder not found or Outlook not available. Check mailbox and path (use Inbox/Subfolder).")
                else:
                    msgs = newest_mail_items(folder, n=int(peek_n))
                    if not msgs:
                        st.warning("No messages found in the selected folder.")
                    else:
                        rows = []
                        for m in msgs:
                            try:
                                sender = resolve_smtp(m) or ""
                                subj = str(getattr(m, "Subject", ""))
                                html = clean_html_from_mail_item(m)
                                # Detected issuer and rows if using detected vs override
                                from app_core.extractors import extract_for_sender as _efs
                                det_df, det_issuer = _efs(html, sender)
                                # Use pipeline normalize path to count rows reliably
                                from app_core.pipeline import run_on_html as _roh
                                out_det = _roh(html, sender)
                                out_over = _roh(html, sender, issuer_override=issuer_override)
                                rows.append({
                                    "subject": subj[:120],
                                    "sender": sender,
                                    "detected_issuer": det_issuer or "-",
                                    "rows_detected": 0 if (out_det is None) else len(out_det),
                                    "rows_override": 0 if (out_over is None) else len(out_over),
                                })
                            except Exception:
                                continue
                        if rows:
                            st.dataframe(pd.DataFrame(rows), use_container_width=True)
                        else:
                            st.info("No peek rows to show.")
            except Exception as e:
                st.error(f"Diagnostics failed: {e}")


with tab_parser:
    st.subheader("Parser")
    cols_btn = st.columns([1, 4])
    with cols_btn[0]:
        start = st.button("Start Parsing", key="start_parsing_btn")

    if start:
        result = run_outlook(
            mailbox,
            [p for p in folder_path.split('/') if p],
            max_emails=n,
            issuer_override=issuer_override,
        )
        # Support both new (df, stats) and old (df) return signatures
        if isinstance(result, tuple) and len(result) == 2:
            df_all, stats = result
        else:
            df_all, stats = result, {"retrieved_emails": n, "parsed_emails": 0, "parsed_rows": len(result) if hasattr(result, "__len__") else 0}

        if df_all is None or df_all.empty:
            st.warning("No data parsed from Outlook.")
        else:
            # Store results silently (no green success banner per request)
            st.session_state["df_all"] = df_all
        # Always show processing stats for clarity
        st.caption(
            f"Processed {stats.get('retrieved_emails', 0)} emails • Parsed {stats.get('parsed_emails', 0)} emails • Parsed data rows {stats.get('parsed_rows', 0)}"
        )

    # Removed 'Load via Graph' from this tab as requested

    # Render results and selection UI within this tab
    def _render_outlook_selection_ui_parser() -> None:
        df_all = st.session_state.get("df_all")
        if not isinstance(df_all, pd.DataFrame) or df_all.empty:
            st.info("Provide input and click Start Parsing to begin.")
            return

        st.subheader("Select Versions")
        # Variable to solve for
        possible_vars = [c for c in ["coupon", "strike", "reoffer", "barrier"] if c in df_all.columns]
        if not possible_vars:
            st.warning("No standard metric columns (coupon, strike, reoffer, barrier) found in parsed data. Showing parsed table.")
            st.dataframe(df_all, use_container_width=True)
            st.download_button(
                "Download Parsed CSV",
                data=df_all.to_csv(index=False).encode("utf-8"),
                file_name="parsed_raw.csv",
                mime="text/csv",
                key="dl_csv_parsed_raw_parser",
            )
            return
        solve_var = st.selectbox(
            "Select variable you are solving for:", options=possible_vars, index=0, key="solve_var_parser"
        )

        # Key components
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
                    val = st.checkbox(
                        label,
                        value=checked,
                        disabled=disabled,
                        help=help_map.get(name),
                        key=f"ck_{name}_parser",
                    )
                if val:
                    components.append(name)
                    selected_labels.append(label)
        st.caption("Current key: " + " + ".join(selected_labels) if components else "Current key: (none)")

        # Grouping for versions
        def _get_version_labels_and_map(df: pd.DataFrame, components: list[str], solve_var: str):
            tmp = df.copy()
            tmp = tmp.assign(_version_key=_make_key(tmp, components))
            asc_local = False if solve_var == "coupon" else True
            try:
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
            except Exception:
                grp = (
                    tmp.groupby("_version_key")
                    .agg(rows=(solve_var, "size"), metric=(solve_var, "mean"))
                    .reset_index()
                    .sort_values(by=["metric"], ascending=asc_local)
                )
            recs = grp.to_dict("records")
            def _label(rec: dict) -> str:
                key = rec.get("_version_key", "")
                key_disp = _bold_text(str(key))
                cnt = int(rec.get("issuers", 0))
                ilist = list(rec.get("issuer_list", [])) if "issuer_list" in rec else []
                if len(ilist) > 10:
                    ilist = ilist[:10] + [f"+{len(ilist)-10}"]
                issuers_txt = ", ".join(ilist) if ilist else "-"
                return f"{key_disp} ({cnt} issuers: {issuers_txt})"
            labels = [_label(r) for r in recs]
            vmap = {lab: r.get("_version_key", "") for lab, r in zip(labels, recs)}
            return labels, vmap, recs

        version_labels, version_map, recs_internal = _get_version_labels_and_map(df_all, components, solve_var)

        mode = st.radio("Mode:", options=["Single version", "Compare versions"], index=0, key="mode_parser")

        if mode == "Single version":
            selected_label = st.selectbox(
                "Choose version",
                options=(version_labels or ["(no versions)"]),
                help="Labels show the version key plus the issuers included (hover to read full label).",
                key="sel_version_parser",
            )
            selected_versions = [version_map.get(selected_label, "")] if version_labels else []
        else:
            selected_labels_multi = st.multiselect(
                "Choose versions",
                options=version_labels,
                default=version_labels[:2],
                help="Labels include issuer abbreviations for each version.",
                key="sel_versions_multi_parser",
            )
            selected_versions = [version_map[l] for l in selected_labels_multi]
            if selected_labels_multi:
                items = []
                for idx, lab in enumerate(selected_labels_multi, start=1):
                    rec = None
                    try:
                        for l, r in zip(version_labels, recs_internal):
                            if l == lab:
                                rec = r
                                break
                    except Exception:
                        rec = None
                    ilist = list(rec.get("issuer_list", [])) if rec is not None else []
                    items.append(f"V{idx}: {', '.join(ilist) if ilist else '-'}")
                st.caption("Issuers per selected version → " + " | ".join(items))

        df_view = df_all.copy()
        df_view = df_view.assign(_version_key=_make_key(df_view, components))

        if st.button("Confirm Selection", key="confirm_btn_parser"):
            out = df_view[df_view["_version_key"].isin(selected_versions)].copy() if selected_versions else df_view.copy()
            _metric = (solve_var or "coupon").lower()
            asc = False if _metric == "coupon" else True
            if solve_var in out.columns:
                out = out.sort_values(by=[solve_var], ascending=asc)
            if "issuer" in out.columns:
                out["issuer"] = out["issuer"].apply(_abbr)
            out_display = out.where(out.notna(), "NA")
            st.session_state["confirmed_out"] = out
            st.session_state["confirmed_out_display"] = out_display
            st.session_state["confirmed_solve_var"] = solve_var
            st.session_state["confirmed_mode"] = mode
            if mode == "Single version":
                st.session_state["confirmed_versions"] = selected_versions
                st.session_state["confirmed_version_titles"] = ["V1"]
            else:
                st.session_state["confirmed_versions"] = selected_versions
                st.session_state["confirmed_version_titles"] = [f"V{i+1}" for i in range(len(selected_versions))]
            st.session_state["confirmed"] = True

            if st.session_state.get("confirmed") and isinstance(st.session_state.get("confirmed_out_display"), pd.DataFrame):
                out = st.session_state["confirmed_out"]
                out_display = st.session_state["confirmed_out_display"]
                st.subheader("Result Table (Confirmed)")
                confirmed_solve_var = st.session_state.get("confirmed_solve_var", "coupon")
                confirmed_mode = st.session_state.get("confirmed_mode", "Single version")
                if confirmed_mode == "Compare versions":
                    versions = st.session_state.get("confirmed_versions", [])
                    titles = st.session_state.get("confirmed_version_titles", [])
                    issuer_table_df = _build_issuer_compare_table_df(out, confirmed_solve_var, versions, titles)
                else:
                    issuer_table_df = _build_issuer_table_df(out, confirmed_solve_var)
                st.dataframe(issuer_table_df, use_container_width=True)
                csv_persist = issuer_table_df.to_csv(index=False).encode("utf-8")
                file_metric = ("coupon" if confirmed_solve_var == "coupon" else confirmed_solve_var.title())
                st.download_button(
                    "Download CSV (Confirmed)",
                    data=csv_persist,
                    file_name=f"issuer_rating_{file_metric}.csv",
                    mime="text/csv",
                    key="dl_csv_confirmed_parser",
                )

                st.subheader("Email Output")
                template_path = st.text_input(
                    "Outlook template (.oft) path",
                    value=st.session_state.get(
                        "template_path",
                        r"C:\\Users\\yann.boulbenmeyer\\OneDrive - Calebo Capital AG\\Dokumente\\Email to Send Templates\\Issuers.oft",
                    ),
                    key="template_path_parser",
                    help="Provide the .oft template used to compose the email",
                )
                if st.button("Generate Outlook Email", key="gen_email_btn_parser"):
                    try:
                        import os
                        if not os.path.exists(template_path):
                            raise FileNotFoundError(f"Template not found: {template_path}")
                        import pythoncom  # type: ignore
                        pythoncom.CoInitialize()
                        import win32com.client as win32  # type: ignore
                        outlook = win32.Dispatch("Outlook.Application")
                        mail = outlook.CreateItemFromTemplate(template_path)
                        html_table = issuer_table_df.to_html(index=False)
                        try:
                            mail.HTMLBody = f"<div>{html_table}</div>" + mail.HTMLBody
                        except Exception:
                            mail.Body = issuer_table_df.to_csv(index=False) + "\n\n" + getattr(mail, "Body", "")
                        mail.Display()
                        st.success("Outlook email window opened from template.")
                    except Exception as e:
                        st.error(f"Failed to generate Outlook email: {e}")
                    finally:
                        try:
                            pythoncom.CoUninitialize()
                        except Exception:
                            pass
                st.subheader(f"Result Table (Solved for {confirmed_solve_var})")
                st.dataframe(out_display, use_container_width=True)
                csv_full = out_display.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Download Full CSV",
                    data=csv_full,
                    file_name="parsed_selection.csv",
                    mime="text/csv",
                    key="dl_csv_full_confirmed_parser",
                )
        
        
    _render_outlook_selection_ui_parser()


with tab_graph:
    st.subheader("Graph Parser")
    # Require sign-in
    token = st.session_state.get("graph_token")
    if not (token and token.get("access_token")):
        st.warning("You are not signed in to Microsoft Graph.")
        try:
            conf_local = graph_load_config()
            redirect_uri_local = conf_local.get("redirect_uri") or "http://localhost:8501"
            app_local = graph_build_app(conf_local)
            auth_url_local = graph_build_auth_url(app_local, GRAPH_MAIL_SCOPES, redirect_uri_local)
            # Offer sign-in right here in the tab
            st.link_button("Sign in with Microsoft", auth_url_local)
            st.caption(f"Redirect URI: {redirect_uri_local}")
        except Exception as e:
            st.error(f"Configure Azure app in .streamlit/secrets.toml: {e}")
        # Do NOT stop the whole app; allow other tabs/sections to render
        # so Outlook parsing results can be seen without Graph sign-in.
        pass
    # Controls
    colg = st.columns([1,1,4])
    with colg[0]:
        start_graph_tab = st.button("Start Parsing via Graph", key="start_graph_tab_btn")
    with colg[1]:
        if st.button("Sign out", key="graph_signout_btn"):
            st.session_state.pop("graph_token", None)
            st.session_state.pop("graph_me", None)
            st.rerun()

    if start_graph_tab:
        # Guard: only proceed if a Graph token is present
        if not (token and token.get("access_token")):
            st.warning("You are not signed in to Microsoft Graph.")
        else:
            try:
                access_token = token.get("access_token")
                g_path = st.session_state.get("graph_folder_path") or "Inbox"
                g_n = int(st.session_state.get("graph_n_slider") or 40)
                folder_id = _graph_find_folder_by_path(access_token, g_path)
                if not folder_id:
                    st.warning(f"Graph folder not found: {g_path}")
                else:
                    msgs = _graph_get_messages(access_token, folder_id, top=g_n)
                    frames, parsed = [], 0
                    for msg in msgs:
                        html, sender = _graph_extract_html_and_sender(msg)
                        if not html:
                            continue
                        df = run_on_html(html, sender)
                        if df is not None and not df.empty:
                            frames.append(df)
                            parsed += 1
                    stats = {"retrieved_emails": len(msgs), "parsed_emails": parsed, "parsed_rows": int(sum(len(f) for f in frames)) if frames else 0}
                    if frames:
                        st.session_state["df_all_graph"] = pd.concat(frames, ignore_index=True)
                        st.caption(f"Processed {stats['retrieved_emails']} Graph emails • Parsed {stats['parsed_emails']} • Rows {stats['parsed_rows']}")
                    else:
                        st.warning("No data parsed from Graph messages.")
            except Exception as e:
                st.exception(e)

    df_all_g = st.session_state.get("df_all_graph")
    if not isinstance(df_all_g, pd.DataFrame) or df_all_g.empty:
        st.info("Click 'Start Parsing via Graph' to load and parse emails.")
        # Do not halt the entire app if Graph data is not loaded
        st.caption("Graph data not loaded — Outlook parsing can still be used.")
        st.write("")
        # Skip rendering the Graph selection UI when empty
        st.experimental_rerun if False else None
        
        # Short-circuit Graph tab rendering
        pass
    else:
        st.subheader("Select Versions (Graph)")
        possible_vars_g = [c for c in ["coupon", "strike", "reoffer", "barrier"] if c in df_all_g.columns]
        solve_var_g = st.selectbox("Select variable you are solving for:", options=possible_vars_g, index=0, key="g_solve_var")

        st.caption("Select Key Components:")
        label_map_g = {
            "underlyings": "Underlyings",
            "tenor": "Tenor",
            "barrier_type": "Barrier type",
            "barrier": "Barrier",
            "no_call_period": "No call period",
            "strike": "Strike",
            "coupon": "Coupon",
            "reoffer": "Reoffer",
        }
        help_map_g = {
            "underlyings": "Group by the underlying basket (codes 1..5)",
            "tenor": "Tenor in months",
            "barrier_type": "European/American",
            "barrier": "Barrier level (%)",
            "no_call_period": "Autocall from period (months)",
            "strike": "Put strike (%)",
            "coupon": "Coupon % p.a.",
            "reoffer": "Reoffer (%)",
        }
        comp_order_g = ["underlyings", "tenor", "barrier_type", "barrier", "no_call_period", "strike", "coupon", "reoffer"]
        comp_default_g = {k: True for k in comp_order_g}; comp_default_g["reoffer"] = False
        components_g, selected_labels_g = [], []
        per_row = 4
        for row_start in range(0, len(comp_order_g), per_row):
            row_items = comp_order_g[row_start:row_start+per_row]
            ccols = st.columns(len(row_items))
            for j, name in enumerate(row_items):
                label = label_map_g[name]
                disabled = (name == solve_var_g)
                checked = comp_default_g[name] and not disabled
                with ccols[j]:
                    val = st.checkbox(label, value=checked, disabled=disabled, help=help_map_g.get(name), key=f"g_ck_{name}")
                if val:
                    components_g.append(name)
                    selected_labels_g.append(label)
        st.caption("Current key: " + " + ".join(selected_labels_g) if components_g else "Current key: (none)")

        # Build grouping based on selected key for preview/selection
        def _get_version_labels_and_map_g(df: pd.DataFrame, components: list[str], solve_var: str):
            tmp = df.copy()
            tmp = tmp.assign(_version_key=_make_key(tmp, components))
            asc_local = False if solve_var == "coupon" else True
            try:
                grp = (
                    tmp.groupby("_version_key")
                    .agg(
                        rows=(solve_var, "size"),
                        issuers=("issuer", lambda s: len(set([str(x) for x in s if pd.notna(x)]))),
                        issuer_list=("issuer", lambda s: sorted({ _abbr(x) for x in s if pd.notna(x) and str(x).strip() })),
                        metric=(solve_var, "mean"),
                    )
                    .reset_index()
                    .sort_values(by=["metric"], ascending=asc_local)
                )
            except Exception:
                grp = (
                    tmp.groupby("_version_key")
                    .agg(
                        rows=(solve_var, "size"),
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
                ilist = list(rec.get("issuer_list", [])) if "issuer_list" in rec else []
                if len(ilist) > 10:
                    ilist = ilist[:10] + [f"+{len(ilist)-10}"]
                issuers_txt = ", ".join(ilist) if ilist else "-"
                return f"{key_disp} ({cnt} issuers: {issuers_txt})"
            labels = [_label(r) for r in recs]
            vmap = {lab: r.get("_version_key", "") for lab, r in zip(labels, recs)}
            return labels, vmap, recs

        version_labels_g, version_map_g, recs_internal_g = _get_version_labels_and_map_g(df_all_g, components_g, solve_var_g)

        mode_g = st.radio("Mode:", options=["Single version", "Compare versions"], index=0, key="g_mode")
        if mode_g == "Single version":
            selected_label_g = st.selectbox(
                "Choose version",
                options=(version_labels_g or ["(no versions)"]),
                help="Labels show the version key plus the issuers included (hover to read full label).",
                key="g_sel_version"
            )
            selected_versions_g = [version_map_g.get(selected_label_g, "")] if version_labels_g else []
        else:
            selected_labels_multi_g = st.multiselect(
                "Choose versions",
                options=version_labels_g,
                default=version_labels_g[:2],
                help="Labels include issuer abbreviations for each version.",
                key="g_sel_versions_multi"
            )
            selected_versions_g = [version_map_g[l] for l in selected_labels_multi_g]
            if selected_labels_multi_g:
                items = []
                for idx, lab in enumerate(selected_labels_multi_g, start=1):
                    rec = None
                    try:
                        for l, r in zip(version_labels_g, recs_internal_g):
                            if l == lab:
                                rec = r
                                break
                    except Exception:
                        rec = None
                    ilist = list(rec.get("issuer_list", [])) if rec is not None else []
                    items.append(f"V{idx}: {', '.join(ilist) if ilist else '-'}")
                st.caption("Issuers per selected version → " + " | ".join(items))

    try:
        df_view_g = df_all_g.copy()
        df_view_g = df_view_g.assign(_version_key=_make_key(df_view_g, components_g))

        if st.button("Confirm Selection (Graph)", key="g_confirm_btn"):
            out_g = df_view_g[df_view_g["_version_key"].isin(selected_versions_g)].copy() if selected_versions_g else df_view_g.copy()
            _metric_g = (solve_var_g or "coupon").lower()
            asc_g = False if _metric_g == "coupon" else True
            if solve_var_g in out_g.columns:
                out_g = out_g.sort_values(by=[solve_var_g], ascending=asc_g)
            if "issuer" in out_g.columns:
                out_g["issuer"] = out_g["issuer"].apply(_abbr)
            out_display_g = out_g.where(out_g.notna(), "NA")
            st.session_state["g_confirmed_out"] = out_g
            st.session_state["g_confirmed_out_display"] = out_display_g
            st.session_state["g_confirmed_solve_var"] = solve_var_g
            st.session_state["g_confirmed_mode"] = mode_g
            if mode_g == "Single version":
                st.session_state["g_confirmed_versions"] = selected_versions_g
                st.session_state["g_confirmed_version_titles"] = ["V1"]
            else:
                st.session_state["g_confirmed_versions"] = selected_versions_g
                st.session_state["g_confirmed_version_titles"] = [f"V{i+1}" for i in range(len(selected_versions_g))]
            st.session_state["g_confirmed"] = True

            if st.session_state.get("g_confirmed") and isinstance(st.session_state.get("g_confirmed_out_display"), pd.DataFrame):
                out_g = st.session_state["g_confirmed_out"]
                out_display_g = st.session_state["g_confirmed_out_display"]

                st.subheader("Result Table (Confirmed, Graph)")
                confirmed_solve_var_g = st.session_state.get("g_confirmed_solve_var", "coupon")
                confirmed_mode_g = st.session_state.get("g_confirmed_mode", "Single version")
                if confirmed_mode_g == "Compare versions":
                    versions_g = st.session_state.get("g_confirmed_versions", [])
                    titles_g = st.session_state.get("g_confirmed_version_titles", [])
                    issuer_table_df_g = _build_issuer_compare_table_df(out_g, confirmed_solve_var_g, versions_g, titles_g)
                else:
                    issuer_table_df_g = _build_issuer_table_df(out_g, confirmed_solve_var_g)
                st.dataframe(issuer_table_df_g, use_container_width=True)
                csv_persist_g = issuer_table_df_g.to_csv(index=False).encode("utf-8")
                file_metric_g = ("coupon" if confirmed_solve_var_g == "coupon" else confirmed_solve_var_g.title())
                st.download_button(
                    "Download CSV (Confirmed, Graph)",
                    data=csv_persist_g,
                    file_name=f"issuer_rating_graph_{file_metric_g}.csv",
                    mime="text/csv",
                    key="g_dl_csv_confirmed",
                )

                st.subheader("Email Output (Graph)")
                template_path_g = st.text_input(
                    "Outlook template (.oft) path",
                    value=st.session_state.get(
                        "template_path_graph",
                        r"C:\\Users\\yann.boulbenmeyer\\OneDrive - Calebo Capital AG\\Dokumente\\Email to Send Templates\\Issuers.oft",
                    ),
                    key="template_path_graph",
                    help="Provide the .oft template used to compose the email",
                )
                if st.button("Generate Outlook Email (Graph)", key="g_gen_email_btn"):
                    try:
                        import os
                        if not os.path.exists(template_path_g):
                            raise FileNotFoundError(f"Template not found: {template_path_g}")
                        import pythoncom  # type: ignore
                        pythoncom.CoInitialize()
                        import win32com.client as win32  # type: ignore
                        outlook = win32.Dispatch("Outlook.Application")
                        mail = outlook.CreateItemFromTemplate(template_path_g)
                        html_table = issuer_table_df_g.to_html(index=False)
                        try:
                            mail.HTMLBody = f"<div>{html_table}</div>" + mail.HTMLBody
                        except Exception:
                            mail.Body = issuer_table_df_g.to_csv(index=False) + "\n\n" + getattr(mail, "Body", "")
                        mail.Display()
                        st.success("Outlook email window opened from template.")
                    except Exception as e:
                        st.error(f"Failed to generate Outlook email: {e}")
                    finally:
                        try:
                            pythoncom.CoUninitialize()
                        except Exception:
                            pass

                st.subheader(f"Result Table (Solved for {confirmed_solve_var_g}) — Graph")
                st.dataframe(out_display_g, use_container_width=True)
                csv_full_g = out_display_g.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Download Full CSV (Graph)",
                    data=csv_full_g,
                    file_name="parsed_selection_graph.csv",
                    mime="text/csv",
                    key="g_dl_csv_full_confirmed",
                )
    except Exception:
        # If Graph data is not loaded (df_all_g is None/empty), skip Graph confirm flow
        pass


    df_all = st.session_state.get("df_all")

    if not isinstance(df_all, pd.DataFrame) or df_all.empty:
        st.info("Provide input and click Start Parsing to begin.")
    else:
        st.subheader("Select Versions")

        # Variable to solve for
        possible_vars = [c for c in ["coupon", "strike", "reoffer", "barrier"] if c in df_all.columns]
        if not possible_vars:
            st.warning("No standard metric columns (coupon, strike, reoffer, barrier) found in parsed data. Showing parsed table.")
            st.dataframe(df_all, use_container_width=True)
            st.download_button(
                "Download Parsed CSV",
                data=df_all.to_csv(index=False).encode("utf-8"),
                file_name="parsed_raw.csv",
                mime="text/csv",
                key="dl_csv_parsed_raw",
            )
            st.stop()
        solve_var = st.selectbox("Select variable you are solving for:", options=possible_vars, index=0)

        # Key components
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
        # Default selections: everything except Reoffer
        comp_default = {k: True for k in comp_order}
        comp_default["reoffer"] = False
        components, selected_labels = [], []
        # Render as a neat 4x2 grid
        per_row = 4
        for row_start in range(0, len(comp_order), per_row):
            row_items = comp_order[row_start:row_start+per_row]
            ccols = st.columns(len(row_items))
            for j, name in enumerate(row_items):
                label = label_map[name]
                disabled = (name == solve_var)
                checked = comp_default[name] and not disabled
                with ccols[j]:
                    val = st.checkbox(label, value=checked, disabled=disabled, help=help_map.get(name))
                if val:
                    components.append(name)
                    selected_labels.append(label)

        st.caption("Current key: " + " + ".join(selected_labels) if components else "Current key: (none)")

        # Build grouping based on selected key for preview/selection
        def _get_version_labels_and_map(df: pd.DataFrame, components: list[str], solve_var: str):
            tmp = df.copy()
            tmp = tmp.assign(_version_key=_make_key(tmp, components))
            asc_local = False if solve_var == "coupon" else True
            try:
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
            except Exception:
                grp = (
                    tmp.groupby("_version_key")
                    .agg(
                        rows=(solve_var, "size"),
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
                ilist = list(rec.get("issuer_list", [])) if "issuer_list" in rec else []
                if len(ilist) > 10:
                    ilist = ilist[:10] + [f"+{len(ilist)-10}"]
                issuers_txt = ", ".join(ilist) if ilist else "-"
                return f"{key_disp} ({cnt} issuers: {issuers_txt})"
            labels = [_label(r) for r in recs]
            vmap = {lab: r.get("_version_key", "") for lab, r in zip(labels, recs)}
            return labels, vmap, recs

        version_labels, version_map, recs_internal = _get_version_labels_and_map(df_all, components, solve_var)

    # If no data yet, halt rendering of the rest of the section
    if not (isinstance(df_all, pd.DataFrame) and not df_all.empty):
        st.stop()

    mode = st.radio("Mode:", options=["Single version", "Compare versions"], index=0)

    # Ensure defaults without triggering Streamlit magic output
    version_labels = locals().get("version_labels", [])
    version_map = locals().get("version_map", {})

    if mode == "Single version":
        selected_label = st.selectbox(
            "Choose version",
            options=(version_labels or ["(no versions)"]),
            help="Labels show the version key plus the issuers included (hover to read full label).",
        )
        selected_versions = [version_map[selected_label]] if version_labels else []
    else:
        selected_labels_multi = st.multiselect(
            "Choose versions",
            options=version_labels,
            default=version_labels[:2],
            help="Labels include issuer abbreviations for each version.",
        )
        selected_versions = [version_map[l] for l in selected_labels_multi]
        # Show issuers per selected version as mini legend
        if selected_labels_multi:
            items = []
            for idx, lab in enumerate(selected_labels_multi, start=1):
                rec = None
                try:
                    for l, r in zip(version_labels, recs_internal):
                        if l == lab:
                            rec = r
                            break
                except Exception:
                    rec = None
                ilist = list(rec.get("issuer_list", [])) if rec is not None else []
                items.append(f"V{idx}: {', '.join(ilist) if ilist else '-'}")
            st.caption("Issuers per selected version → " + " | ".join(items))

    # Minimal UI: no issuer filter; use full dataset
    df_view = df_all.copy()

    # Recompute key on filtered view for final output
    key_series = _make_key(df_view, components)
    df_view = df_view.assign(_version_key=key_series)

    if st.button("Confirm Selection"):
        out = df_view[df_view["_version_key"].isin(selected_versions)].copy() if selected_versions else df_view.copy()
        # Determine sort direction: coupon desc, others asc
        _metric = (solve_var or "coupon").lower()
        asc = False if _metric == "coupon" else True
        if solve_var in out.columns:
            out = out.sort_values(by=[solve_var], ascending=asc)
        # Replace issuer names by uppercase abbreviations and display NA
        if "issuer" in out.columns:
            out["issuer"] = out["issuer"].apply(_abbr)
        out_display = out.where(out.notna(), "NA")
        # Persist selection to survive reruns triggered by other buttons
        st.session_state["confirmed_out"] = out
        st.session_state["confirmed_out_display"] = out_display
        st.session_state["confirmed_solve_var"] = solve_var
        st.session_state["confirmed_mode"] = mode
        if mode == "Single version":
            st.session_state["confirmed_versions"] = selected_versions
            st.session_state["confirmed_version_titles"] = ["V1"]
        else:
            st.session_state["confirmed_versions"] = selected_versions
            # Titles V1, V2, V3 ... in the order selected
            st.session_state["confirmed_version_titles"] = [f"V{i+1}" for i in range(len(selected_versions))]
        st.session_state["confirmed"] = True
        # Result and email are shown in the Confirmed section below

    # Persistent actions area: reused after any rerun
        if st.session_state.get("confirmed") and isinstance(st.session_state.get("confirmed_out_display"), pd.DataFrame):
            out = st.session_state["confirmed_out"]
            out_display = st.session_state["confirmed_out_display"]

            st.subheader("Result Table (Confirmed)")
            # Show issuer table: single or compare mode
            confirmed_solve_var = st.session_state.get("confirmed_solve_var", "coupon")
            confirmed_mode = st.session_state.get("confirmed_mode", "Single version")
            if confirmed_mode == "Compare versions":
                versions = st.session_state.get("confirmed_versions", [])
                titles = st.session_state.get("confirmed_version_titles", [])
                issuer_table_df = _build_issuer_compare_table_df(out, confirmed_solve_var, versions, titles)
            else:
                issuer_table_df = _build_issuer_table_df(out, confirmed_solve_var)
            st.dataframe(issuer_table_df, use_container_width=True)
            csv_persist = issuer_table_df.to_csv(index=False).encode("utf-8")
            file_metric = ("coupon" if confirmed_solve_var == "coupon" else confirmed_solve_var.title())
            st.download_button(
                "Download CSV (Confirmed)",
                data=csv_persist,
                file_name=f"issuer_rating_{file_metric}.csv",
                mime="text/csv",
                key="dl_csv_confirmed",
            )

            st.subheader("Email Output")
            template_path = st.text_input(
                "Outlook template (.oft) path",
                value=st.session_state.get(
                    "template_path",
                    r"C:\\Users\\yann.boulbenmeyer\\OneDrive - Calebo Capital AG\\Dokumente\\Email to Send Templates\\Issuers.oft",
                ),
                key="template_path",
                help="Provide the .oft template used to compose the email",
            )

            # Single action: generate Outlook email with the issuer table for the selected metric
            if st.button("Generate Outlook Email", key="gen_email_btn"):
                try:
                    import os
                    if not os.path.exists(template_path):
                        raise FileNotFoundError(f"Template not found: {template_path}")
                    import pythoncom  # type: ignore
                    pythoncom.CoInitialize()
                    import win32com.client as win32  # type: ignore
                    outlook = win32.Dispatch("Outlook.Application")
                    mail = outlook.CreateItemFromTemplate(template_path)
                    html_table = issuer_table_df.to_html(index=False)
                    try:
                        mail.HTMLBody = f"<div>{html_table}</div>" + mail.HTMLBody
                    except Exception:
                        # Fallback to plain text
                        mail.Body = issuer_table_df.to_csv(index=False) + "\n\n" + getattr(mail, "Body", "")
                    mail.Display()
                    st.success("Outlook email window opened from template.")
                except Exception as e:
                    st.error(f"Failed to generate Outlook email: {e}")
                finally:
                    try:
                        pythoncom.CoUninitialize()
                    except Exception:
                        pass
            # Show the full selection table after the confirmed issuer table
            st.subheader(f"Result Table (Solved for {confirmed_solve_var})")
            st.dataframe(out_display, use_container_width=True)
            csv_full = out_display.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download Full CSV",
                data=csv_full,
                file_name="parsed_selection.csv",
                mime="text/csv",
                key="dl_csv_full_confirmed",
            )

            # Debug table B: all rows across all versions, grouped by current key, sorted by issuer then version
            try:
                df_all_dbg = df_all.copy()
                # Attach the current version key using the selected components
                df_all_dbg = df_all_dbg.assign(_version_key=_make_key(df_all_dbg, components))
                if "issuer" in df_all_dbg.columns:
                    df_all_dbg["issuer"] = df_all_dbg["issuer"].apply(_abbr)
                sort_cols = []
                sort_asc = []
                if "issuer" in df_all_dbg.columns:
                    sort_cols.append("issuer"); sort_asc.append(True)
                if "_version_key" in df_all_dbg.columns:
                    sort_cols.append("_version_key"); sort_asc.append(True)
                if confirmed_solve_var in df_all_dbg.columns:
                    sort_cols.append(confirmed_solve_var)
                    sort_asc.append(False if confirmed_solve_var == "coupon" else True)
                if sort_cols:
                    df_all_dbg = df_all_dbg.sort_values(by=sort_cols, ascending=sort_asc, na_position="last")
                df_all_dbg_display = df_all_dbg.where(df_all_dbg.notna(), "NA")
                st.subheader("Debug Table — All Versions (rows by issuer and version)")
                st.dataframe(df_all_dbg_display, use_container_width=True)
                st.download_button(
                    "Download Debug (All Versions)",
                    data=df_all_dbg_display.to_csv(index=False).encode("utf-8"),
                    file_name="debug_all_versions_rows_by_issuer.csv",
                    mime="text/csv",
                    key="dl_csv_debug_all",
                )
            except Exception:
                pass

with tab_outlook:
    st.subheader("Outlook Test")
    st.caption("Click to open a new empty Outlook email. If nothing opens, a detailed error will be shown below.")
    if st.button("Open Blank Outlook Email", key="blank_outlook_btn"):
        try:
            import pythoncom  # type: ignore
            pythoncom.CoInitialize()
            import win32com.client as win32  # type: ignore
            outlook = win32.Dispatch("Outlook.Application")
            mail = outlook.CreateItem(0)  # olMailItem
            mail.Subject = ""
            mail.Body = ""
            mail.Display()
            st.success("Opened a new blank Outlook email.")
        except Exception as e:
            st.exception(e)
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
