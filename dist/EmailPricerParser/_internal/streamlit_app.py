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


st.set_page_config(page_title="Email Pricer Parser", layout="wide")
st.title("Email Pricer Parser")


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
        font-size: 0.85rem !important;
        white-space: nowrap !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


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


start = st.button("Start Parsing")

if start:
    df_all = run_outlook(mailbox, [p for p in folder_path.split('/') if p], max_emails=n)
    if df_all is None or df_all.empty:
        st.warning("No data parsed from Outlook.")
    else:
        st.success(f"Parsed {len(df_all)} rows from Outlook.")
        st.session_state["df_all"] = df_all


df_all = st.session_state.get("df_all")

if isinstance(df_all, pd.DataFrame) and not df_all.empty:
    st.subheader("Select Versions and Sorting")

    # Variable to solve for
    possible_vars = [c for c in ["coupon", "strike", "reoffer", "barrier"] if c in df_all.columns]
    solve_var = st.selectbox("Select variable you are solving for:", options=possible_vars, index=0)

    # Key components
    st.caption("Select Key Components:")
    comp_default = {
        "underlyings": True,
        "tenor": True,
        "barrier_type": True,
        "barrier": True,
        "no_call_period": True,
        "strike": True,
        "coupon": True,
        "reoffer": True,
    }

    comp_names = list(comp_default.keys())
    cols = st.columns(len(comp_names))
    components = []
    selected_labels = []
    for i, name in enumerate(comp_names):
        label = name.replace("_", " ").capitalize()
        disabled = name == solve_var
        checked = comp_default[name] and not disabled
        val = cols[i].checkbox(label, value=checked, disabled=disabled)
        if val:
            components.append(name)
            selected_labels.append(label)

    st.caption("Current key: " + " + ".join(selected_labels) if components else "Current key: (none)")

    # — Choose versions just below key components —
    # Build grouping based on selected key for preview/selection
    df_view_for_versions = df_all.copy()
    version_key_series = _make_key(df_view_for_versions, components)
    df_view_for_versions = df_view_for_versions.assign(_version_key=version_key_series)

    # Default sorting choice here so the version list reflects it
    sort_choice = st.selectbox("Sort by:", options=[f"{solve_var}_desc", f"{solve_var}_asc"], index=0)
    asc = sort_choice.endswith("_asc")

    grp = df_view_for_versions.groupby("_version_key").agg(
        rows=(solve_var, "size"),
        issuers=("issuer", lambda s: len(set([str(x) for x in s if pd.notna(x)]))),
        metric=(solve_var, "mean"),
    ).reset_index().sort_values(by=["metric"], ascending=asc)

    mode = st.radio("Mode:", options=["Single version", "Compare versions"], index=0)

    version_labels = [f"{row['_version_key']} ({row['issuers']} issuers)" for _, row in grp.iterrows()]
    version_map = {label: row["_version_key"] for label, (_, row) in zip(version_labels, grp.iterrows())}

    if mode == "Single version":
        selected_label = st.selectbox("Choose version", options=version_labels)
        selected_versions = [version_map[selected_label]] if version_labels else []
    else:
        selected_labels_multi = st.multiselect("Choose versions", options=version_labels, default=version_labels[:2])
        selected_versions = [version_map[l] for l in selected_labels_multi]

    # Issuer filter and grouping preview
    # Build uppercase abbreviation list for issuer filter
    if "issuer" in df_all.columns:
        issuers_raw = [str(x) for x in df_all["issuer"].dropna().unique()]
        issuers_display = sorted({_abbr(x) for x in issuers_raw})
    else:
        issuers_display = []
    issuer_sel = st.multiselect("Filter issuers (optional)", options=issuers_display, default=issuers_display)

    df_view = df_all.copy()
    if issuer_sel:
        df_view = df_view[df_view["issuer"].apply(lambda x: _abbr(x) in set(issuer_sel))]

    # Recompute key on filtered view for final output
    key_series = _make_key(df_view, components)
    df_view = df_view.assign(_version_key=key_series)

    if st.button("Confirm Selection"):
        out = df_view[df_view["_version_key"].isin(selected_versions)].copy()
        out = out.sort_values(by=[solve_var], ascending=asc)
        # Replace issuer names by uppercase abbreviations and display NA
        if "issuer" in out.columns:
            out["issuer"] = out["issuer"].apply(_abbr)
        out_display = out.where(out.notna(), "NA")
        # Persist selection to survive reruns triggered by other buttons
        st.session_state["confirmed_out"] = out
        st.session_state["confirmed_out_display"] = out_display
        st.session_state["confirmed_solve_var"] = solve_var
        st.session_state["confirmed"] = True
        # Result and email are shown in the Confirmed section below

    # Persistent actions area: reused after any rerun
    if st.session_state.get("confirmed") and isinstance(st.session_state.get("confirmed_out_display"), pd.DataFrame):
        out = st.session_state["confirmed_out"]
        out_display = st.session_state["confirmed_out_display"]

        st.subheader("Result Table (Confirmed)")
        # Show only Emittent / Rating / Coupon in the confirmed table
        # Use the confirmed solve_var to decide sorting
        confirmed_solve_var = st.session_state.get("confirmed_solve_var", "coupon")
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
else:
    st.info("Provide input and click Start Parsing to begin.")
