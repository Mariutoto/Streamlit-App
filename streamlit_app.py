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


with st.sidebar:
    st.header("Input Source")
    source = st.radio(
        "Choose source",
        ["Paste HTML", "Upload File", "Outlook Folder"],
    )

    issuer_keys = [k for k in EXTRACTOR_BY_ISSUER.keys()]
    issuer_override = st.selectbox(
        "Issuer override (optional)",
        [""] + issuer_keys,
        index=0,
        help="If set, forces this issuer's extractor/normalizer",
    )
    issuer_override = issuer_override or None


# Gather input, but only parse when user clicks "Start Parsing"
html_input = None
sender_hint = None

if source == "Paste HTML":
    html_input = st.text_area("Paste HTML body", height=300)
elif source == "Upload File":
    up = st.file_uploader("Upload .html or .eml", type=["html", "htm", "eml"])
    if up is not None:
        content = up.read()
        try:
            text = content.decode("utf-8", errors="ignore")
        except Exception:
            text = str(content)
        if up.name.lower().endswith((".html", ".htm")):
            html_input = text
        elif up.name.lower().endswith(".eml"):
            start = text.lower().find("<html")
            if start != -1:
                html_input = text[start:]
            else:
                st.warning("No HTML part detected in EML; paste HTML manually?")
else:  # Outlook Folder
    st.info("Requires Outlook/pywin32 on this machine.")
    mailbox = st.text_input("Mailbox SMTP or display name", value="boulbenmeyer@calebocapital.ch")
    folder_path = st.text_input("Folder path (use '/' for nesting)", value="Pricer")
    n = st.slider("Fetch newest N emails", 5, 200, 40)


start = st.button("Start Parsing")

if start:
    if source == "Outlook Folder":
        df_all = run_outlook(mailbox, [p for p in folder_path.split('/') if p], max_emails=n)
        if df_all is None or df_all.empty:
            st.warning("No data parsed from Outlook.")
        else:
            st.success(f"Parsed {len(df_all)} rows from Outlook.")
            st.session_state["df_all"] = df_all
    else:
        if not html_input:
            st.warning("Please provide HTML input.")
        else:
            df_one = run_on_html(html_input, sender_hint, issuer_override)
            if df_one is None or df_one.empty:
                st.warning("No table could be extracted/normalized from the input.")
            else:
                st.success(f"Parsed {len(df_one)} rows from input.")
                st.session_state["df_all"] = df_one


df_all = st.session_state.get("df_all")

if isinstance(df_all, pd.DataFrame) and not df_all.empty:
    st.subheader("Select Versions and Sorting")

    # Variable to solve for
    possible_vars = [c for c in ["coupon", "strike", "reoffer", "barrier"] if c in df_all.columns]
    solve_var = st.selectbox("Select variable you are solving for:", options=possible_vars, index=0)

    # Key components
    st.caption("Select key components:")
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

    cols = st.columns(8)
    components = []
    comp_names = list(comp_default.keys())
    for i, name in enumerate(comp_names):
        disabled = name == solve_var
        checked = comp_default[name] and not disabled
        val = cols[i].checkbox(name, value=checked, disabled=disabled)
        if val:
            components.append(name)

    st.caption("Current key: " + " + ".join(components) if components else "Current key: (none)")

    # Issuer filter and grouping preview
    issuers = sorted([x for x in df_all["issuer"].dropna().astype(str).unique()]) if "issuer" in df_all.columns else []
    issuer_sel = st.multiselect("Filter issuers (optional)", options=issuers, default=issuers)

    df_view = df_all.copy()
    if issuer_sel:
        df_view = df_view[df_view["issuer"].astype(str).isin(issuer_sel)]

    key_series = _make_key(df_view, components)
    df_view = df_view.assign(_version_key=key_series)

    grp = df_view.groupby("_version_key").agg(
        rows=(solve_var, "size"),
        issuers=("issuer", lambda s: len(set([str(x) for x in s if pd.notna(x)]))),
        metric=(solve_var, "mean"),
    ).reset_index()

    # Sort choice
    sort_choice = st.selectbox("Sort by:", options=[f"{solve_var}_desc", f"{solve_var}_asc"], index=0)
    asc = sort_choice.endswith("_asc")
    grp = grp.sort_values(by=["metric"], ascending=asc)

    # Mode
    mode = st.radio("Mode:", options=["Single version", "Compare versions"], index=0)

    # Selection of versions
    version_labels = [f"{row['_version_key']} ({row['issuers']} issuers)" for _, row in grp.iterrows()]
    version_map = {label: row["_version_key"] for label, (_, row) in zip(version_labels, grp.iterrows())}

    if mode == "Single version":
        selected_label = st.selectbox("Choose version", options=version_labels)
        selected_versions = [version_map[selected_label]]
    else:
        selected_labels = st.multiselect("Choose versions", options=version_labels, default=version_labels[:2])
        selected_versions = [version_map[l] for l in selected_labels]

    if st.button("Confirm Selection"):
        out = df_view[df_view["_version_key"].isin(selected_versions)].copy()
        out = out.sort_values(by=[solve_var], ascending=asc)
        st.subheader("Result Table")
        st.dataframe(out, use_container_width=True)
        csv = out.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", data=csv, file_name="parsed_selection.csv", mime="text/csv")
else:
    st.info("Provide input and click Start Parsing to begin.")
