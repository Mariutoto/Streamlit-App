from __future__ import annotations

import pandas as pd


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    rename = {
        "Product": "product",
        "Coupon p.a. (%)": "coupon",
        "SnowBall Coupon": "coupon",
        "Currency": "currency",
        "Tenor (M)": "tenor",
        "Tenor (m)": "tenor",
        "Tenor": "tenor",
        "Maturity": "tenor",
        "Strike": "strike",
        "Strike (%)": "strike",
        "KI Barrier (%)": "barrier",
        "Barrier (%)": "barrier",
        "Barrier Type": "barrier_type",
        "Autocall Barrier": "autocall_barrier",
        "Trigger Level (%)": "autocall_barrier",
        "Autocall Frequency": "autocall_frequency",
        "No Call Period": "no_call_period",
        "No Call Periods": "no_call_period",
        "Non Callable Periods": "no_call_period",
        "Fees Upfront/PC": "reoffer",
        "Reoffer (%)": "reoffer",
        "Upfront (%)": "reoffer",
        "Underlyings": "underlyings_raw",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    # Split underlyings if a single field is provided
    if "underlyings_raw" in df.columns:
        split_cols = df["underlyings_raw"].astype(str).str.split(";", expand=True)
        for i, col in enumerate(split_cols.columns, start=1):
            df[f"underlying_{i}"] = split_cols[col].str.strip().replace("", pd.NA)
        df = df.drop(columns=["underlyings_raw"])
    return df

