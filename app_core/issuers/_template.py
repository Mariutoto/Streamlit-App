from __future__ import annotations

import pandas as pd


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Template normalizer: copy df and map issuer-specific columns to canonical ones.

    Implement issuer-specific renames/parsing only here, keep logic minimal.
    Universal cleanup will run afterwards to harmonize types and fill gaps.
    """
    return df.copy()

