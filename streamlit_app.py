import io
import os
from typing import Optional, List

import pandas as pd
import streamlit as st

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
tab_parser, tab_email_pricing, tab_outlook = st.tabs(["Parser", "Email Pricing", "Outlook Test"]) 
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


with tab_parser:
    st.subheader("Parser")
    start = st.button("Start Parsing", key="start_parsing_btn")

    if start:
        result = run_outlook(mailbox, [p for p in folder_path.split('/') if p], max_emails=n)
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


    df_all = st.session_state.get("df_all")

    if not isinstance(df_all, pd.DataFrame) or df_all.empty:
        st.info("Provide input and click Start Parsing to begin.")
    else:
        st.subheader("Select Versions")

        # Variable to solve for
        possible_vars = [c for c in ["coupon", "strike", "reoffer", "barrier"] if c in df_all.columns]
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
