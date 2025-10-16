from __future__ import annotations

import pandas as pd


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    rename = {
        "Product": "product",
        "PRODUCT": "product",
        "Currency": "currency",
        "Tenor": "tenor",
        "Tenor (m)": "tenor",
        "Tenor (months)": "tenor",
        "Tenor m": "tenor",
        "BBG Code 1 +": "underlying_1",
        "BBG Code 1": "underlying_1",
        "BBG Code 2": "underlying_2",
        "BBG Code 3": "underlying_3",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    return df

