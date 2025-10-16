from __future__ import annotations

import pandas as pd


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Map common Citi column labels to canonical names, keep light; universal cleanup follows
    rename = {
        "Product": "product",
        "Product Name": "product",
        "Currency": "currency",
        "Ccy": "currency",
        "Tenor (m)": "tenor",
        "Tenor": "tenor",
        "Tenor (months)": "tenor",
        "BBG Code 1": "underlying_1",
        "BBG Code 2": "underlying_2",
        "BBG Code 3": "underlying_3",
        "BBG Code 4": "underlying_4",
        "BBG Code 5": "underlying_5",
        "Strike (%)": "strike",
        "Strike %": "strike",
        "Strike": "strike",
        "Barrier Type": "barrier_type",
        "KI Barrier (%)": "barrier",
        "Barrier (%)": "barrier",
        "KI Barrier": "barrier",
        "Autocall Barrier (%)": "autocall_barrier",
        "KO Barrier (%)": "autocall_barrier",
        "Early Termination Level (%)": "autocall_barrier",
        "Autocall Frequency": "autocall_frequency",
        "Observation Frequency (m)": "autocall_frequency",
        "KO Frequency": "autocall_frequency",
        "No Call Period": "no_call_period",
        "Non Callable Periods": "no_call_period",
        "Non Autocallable Period": "no_call_period",
        "Coupon p.a. (%)": "coupon",
        "Coupon (%)": "coupon",
        "Fixed Coupon p.a. (%)": "coupon",
        "Reoffer (%)": "reoffer",
        "Upfront (%)": "reoffer",
        "Reoffer": "reoffer",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    return df

