def normalize_citi(df):
    df = df.copy()

    # --- Define column variants ---
    rename_options = {
        "product": ["Product", "Product Name"],
        "currency": ["Currency", "Ccy"],
        "tenor": ["Tenor (m)", "Tenor", "Tenor (months)"],
        "underlying_1": ["BBG Code 1", "Underlying 1"],
        "underlying_2": ["BBG Code 2", "Underlying 2"],
        "underlying_3": ["BBG Code 3", "Underlying 3"],
        "underlying_4": ["BBG Code 4", "Underlying 4"],
        "underlying_5": ["BBG Code 5", "Underlying 5"],
        "strike": ["Strike (%)", "Strike %", "Strike"],
        "barrier_type": ["Barrier Type"],
        "barrier": ["KI Barrier (%)", "Barrier (%)", "KI Barrier"],
        "autocall_barrier": ["Autocall Barrier (%)", "KO Barrier (%)", "Early Termination Level (%)"],
        "autocall_frequency": ["Autocall Frequency", "Observation Frequency (m)", "KO Frequency"],
        "no_call_period": ["No Call Period", "Non Callable Periods", "Non Autocallable Period"],
        "coupon": ["Coupon p.a. (%)", "Coupon (%)", "Fixed Coupon p.a. (%)"],
        # Include both Reoffer (%) and Upfront (%)
        "reoffer": ["Reoffer (%)", "Upfront (%)", "Reoffer"],
    }

    # --- Map each variant to the canonical name ---
    rename_map = {}
    for target, variants in rename_options.items():
        for variant in variants:
            if variant in df.columns:
                rename_map[variant] = target

    df = df.rename(columns=rename_map)

    if "reoffer" in df.columns:
        df["reoffer"] = pd.to_numeric(
            df["reoffer"].astype(str).str.replace("%", "", regex=False),
            errors="coerce"
        )
        df["reoffer"] = 100 - df["reoffer"]

    # --- Ensure all required columns exist ---
    for col in rename_options.keys():
        if col not in df.columns:
            df[col] = pd.NA

    return df


def normalize_natixis(df):
    df = df.copy()

    # --- define possible variants per logical column ---
    rename_options = {
        "product": ["Ref", "Product", "Product Name"],
        "coupon": ["Coupon p.a. (%)", "Fixed Coupon p.a. (%)", "Phoenix Coupon p.a. (%)", "Coupon (%)", "Coupon p.a"],
        "currency": ["Currency", "Ccy"],
        "tenor": ["Tenor (m)", "Tenor", "Maturity (m)", "Tenor in months"],
        "strike": ["Strike (%)", "Strike %", "Strike Level"],
        "barrier": ["KI Barrier (%)", "Barrier Level", "Phoenix Barrier Level (%)", "Barrier (%)", "KI Barrier"],
        "reoffer": ["Reoffer (%)", "Reoffer", "Issue Price (%)", "Reoffer Price"],
        "underlying_1": ["BBG Code 1", "Underlying 1", "Underlying_1", "Ticker 1"],
        "underlying_2": ["BBG Code 2", "Underlying 2", "Underlying_2", "Ticker 2"],
        "underlying_3": ["BBG Code 3", "Underlying 3", "Underlying_3", "Ticker 3"],
        "underlying_4": ["BBG Code 4", "Underlying 4", "Underlying_4", "Ticker 4"],
        "underlying_5": ["BBG Code 5", "Underlying 5", "Underlying_5", "Ticker 5"],
        "barrier_type": ["Barrier Type", "KI Type"],
        "autocall_barrier": ["Early Termination Level (%)", "Autocall Level (%)", "Autocall Trigger (%)"],
        "autocall_frequency": ["Early Termination Period", "KO Frequency", "Autocall Frequency"],
        "no_call_period": ["Non Autocallable Period", "Non callable Period", "No Call Period"],
        "memory_coupon": ["Memory coupon", "Memory Coupon", "Has Memory"],
        "basket_type": ["Basket Type", "Underlying Basket Type"],
        "settlement": ["Settlement", "Settlement Type"],
        "message": ["Message", "Comments", "Remarks"],
        "is_leveraged": ["Is Leveraged", "Leverage"],
        "coupon_frequency": ["Coupon Frequency", "Payment Frequency"],
    }

    # --- build rename map from first matching variant ---
    rename_map = {}
    for target, variants in rename_options.items():
        for variant in variants:
            if variant in df.columns:
                rename_map[variant] = target
                break

    df = df.rename(columns=rename_map)

    return df


def normalize_bofa(df):
    df = df.copy()

    rename_options = {
        "product": ["Product"],
        "coupon": ["Coupon p.a. (%)", "SnowBall Coupon"],
        "currency": ["Currency"],
        "tenor": ["Tenor (M)", "Tenor (m)", "Tenor", "Maturity"],
        "strike": ["Strike", "Strike (%)"],
        "barrier": ["KI Barrier (%)", "Barrier (%)"],
        "barrier_type": ["Barrier Type"],
        "autocall_barrier": ["Autocall Barrier", "Trigger Level (%)"],
        "autocall_frequency": ["Autocall Frequency"],
        "no_call_period": ["No Call Period", "No Call Periods", "Non Callable Periods"],
        "reoffer": ["Fees Upfront/PC", "Reoffer (%)", "Upfront (%)"],
        "underlyings_raw": ["Underlyings"],
    }

    rename_map = {}
    for target, variants in rename_options.items():
        for variant in variants:
            if variant in df.columns:
                rename_map[variant] = target
                break
    df = df.rename(columns=rename_map)

    # --- Handle reoffer ---
    if "reoffer" in df.columns:
        df["reoffer"] = (
            df["reoffer"].astype(str)
            .str.replace("%", "", regex=False)
            .str.replace(",", ".", regex=False)
        )
        df["reoffer"] = pd.to_numeric(df["reoffer"], errors="coerce")
        df.loc[df["reoffer"] <= 20, "reoffer"] = 100 - df["reoffer"]

    # --- Split underlyings ---
    if "underlyings_raw" in df.columns:
        split_cols = df["underlyings_raw"].astype(str).str.split(";", expand=True)
        for i, col in enumerate(split_cols.columns, start=1):
            df[f"underlying_{i}"] = (
                split_cols[col]
                .str.strip()
                .str.replace(" Index", "", regex=False)
                .str.replace(" Equity", "", regex=False)
                .replace("", pd.NA)
            )
        df = df.drop(columns=["underlyings_raw"])

    # --- Normalize barrier type ---
    if "barrier_type" in df.columns:
        df["barrier_type"] = (
            df["barrier_type"]
            .astype(str)
            .str.strip()
            .replace({
                "Continuous": "American",
                "American Intraday": "American",
                "European Intraday": "European",
            })
        )

    # --- Fix BofA no_call_period (autocall starts after X months) ---
    if "no_call_period" in df.columns:
        df["no_call_period"] = (
            df["no_call_period"]
            .astype(str)
            .str.replace("m", "", case=False, regex=False)
        )
        df["no_call_period"] = pd.to_numeric(df["no_call_period"], errors="coerce")

        freq_to_months = {
            "Monthly": 1,
            "Quarterly": 3,
            "Semi-Annual": 6,
            "Annual": 12,
        }

        def convert_no_call(row):
            months = row.get("no_call_period", None)
            freq = row.get("autocall_frequency", "")
            if pd.isna(months):
                return pd.NA
            months_per_period = freq_to_months.get(str(freq).strip().title(), 6)
            # first call after X months → skip X/months_per_period periods minus 1 (because the first call happens *after* that)
            periods_skipped = months / months_per_period
            return max(round(periods_skipped - 1), 0)
        
                    # (10.10) Adjusted logic:
            # BofA defines 'No Call Periods' as the time *until the first call starts*,
            # not the count of fully non-callable periods.
            # Example: Monthly autocall, tenor 6m, no-call 3m → first call at month 3,
            # meaning 2 full periods skipped (so output must be 2, not 0.5).

        df["no_call_period"] = df.apply(convert_no_call, axis=1).astype("Int64")

    return df


def normalize_socgen(df):
    df = df.copy()

    # --- Define possible variants per logical column ---
    rename_options = {
        "product": ["Product", "PRODUCT"],
        "currency": ["Currency"],
        "tenor": ["Tenor", "Tenor (m)", "Tenor (months)", "Tenor m"],
        "underlying_1": ["BBG Code 1 +", "BBG Code 1"],
        "underlying_2": ["BBG Code 2"],
        "underlying_3": ["BBG Code 3"],
        "underlying_4": ["BBG Code 4"],
        "underlying_5": ["BBG Code 5"],
        "strike": ["Strike (%)", "Put Strike (%)", "Strike %", "Strike"],
        "barrier_type": ["Barrier Type"],
        "barrier": ["KI Barrier (%)", "Barrier (%)"],
        "autocall_barrier": ["Autocall Level (%)", "Early Termination Level (%)"],
        "autocall_frequency": [
            "Frequency",
            "Coupon Frequency",
            "Early Termination Period",
        ],
        "no_call_period": [
            "Autocall From Period",
            "Callable by issuer from Period",
            "Non Autocallable Period",
            "No Call Period",
            "Non Callable Period",
        ],
        "coupon": ["Coupon p.a. (%)", "Coupon (% p.a.)", "Coupon (%)", "Coupon"],
        "reoffer": ["Reoffer (%)", "Reoffer"],
    }

    # --- Build rename map dynamically ---
    rename_map = {}
    for target, variants in rename_options.items():
        for v in variants:
            if v in df.columns:
                rename_map[v] = target
                break

    df = df.rename(columns=rename_map)

    # --- Numeric cleanup ---
    for col in ["coupon", "strike", "barrier", "reoffer"]:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace("%", "", regex=False)
                .str.replace(",", ".", regex=False)
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # --- Clean barrier values (set 0.00 or 0 to NA) ---
    if "barrier" in df.columns:
        df.loc[df["barrier"].isin([0, 0.0]), "barrier"] = pd.NA

    # --- Adjusted logic for SG no_call_period ---
    if "no_call_period" in df.columns:
        df["no_call_period"] = pd.to_numeric(df["no_call_period"], errors="coerce")

        mask = df["no_call_period"].notna() & (df["no_call_period"] > 0)
        df.loc[mask, "no_call_period"] = df.loc[mask, "no_call_period"] - 1
        df["no_call_period"] = df["no_call_period"].round().astype("Int64")

    # --- Clean up barrier type naming ---
    if "barrier_type" in df.columns:
        df["barrier_type"] = (
            df["barrier_type"]
            .astype(str)
            .replace({"Continuous": "American", "At Expiry": "European"})
        )

    return df


import pandas as pd

def normalize_gs(df):
    df = df.copy()

    # --- Standardize column names ---
    rename_options = {
        "product": ["Product", "Prod"],
        "wrapper": ["Wrapper"],
        "currency": ["Currency", "CCY", "Ccy"],
        "tenor": ["Tenor (m)", "Tenor (M)", "Tenor", "Tenor (months)"],
        "underlying_1": ["BBG Code 1", "Underlying 1", "Ticker 1"],
        "underlying_2": ["BBG Code 2", "Underlying 2", "Ticker 2"],
        "underlying_3": ["BBG Code 3", "Underlying 3", "Ticker 3"],
        "underlying_4": ["BBG Code 4", "Underlying 4", "Ticker 4"],
        "underlying_5": ["BBG Code 5", "Underlying 5", "Ticker 5"],
        "strike": ["Strike(%)", "Strike (%)", "Strike %"],
        "barrier_type": ["Barrier Type", "KI Type"],
        "barrier": ["KI Barrier(%)", "Barrier(%)", "Barrier %", "KI Level(%)"],
        "autocall_frequency": ["Early Termination Period", "Coupon Frequency", "Frequency"],
        "no_call_period": ["Non Autocallable Period", "NoCall Period", "Autocall from Period X"],
        "autocall_barrier": ["Early Termination Level(%)", "Autocall Level(%)", "Trigger Level(%)"],
        "coupon": ["Coupon p.a.(%)", "Coupon p.a. (%)", "Coupon (%)", "Coupon"],
        "memory_coupon": ["Memory Coupon", "Memory", "Coupon Memory", "Has Memory"],
        "reoffer": ["Reoffer(%)", "Reoffer (%)", "Issue Price", "Price (%)", "Note Price"],
        "notional": ["Notional", "Size", "Nominal", "Trade Size"],
        "issuer": ["Issuer", "Emittent"],
        "systemremark": ["SystemRemark", "Remark", "Note", "Comments"],
    }

    for new_col, variants in rename_options.items():
        for v in variants:
            if v in df.columns:
                df = df.rename(columns={v: new_col})
                break

    # --- Barrier cleanup: replace 100 with NA ---
    if "barrier" in df.columns:
        df["barrier"] = pd.to_numeric(df["barrier"], errors="coerce")
        df.loc[df["barrier"] == 100, "barrier"] = pd.NA

    # --- Numeric cleanup for reoffer and coupon ---
    for col in ["reoffer", "coupon", "strike"]:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace("%", "", regex=False)
                .str.strip()
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")
    
    df = df.loc[:, ~df.columns.duplicated()]

    return df

def normalize_bnp(df):
    df = df.copy()

    # --- Define possible variants per logical column ---
    rename_options = {
        "product": ["PRODUCT"],
        "currency": ["Currency"],
        "tenor": ["Tenor", "Tenor (m)", "Tenor (months)", "Tenor m"],
        "underlying_1": ["BBG Code 1 +", "BBG Code 1"],
        "underlying_2": ["BBG Code 2"],
        "underlying_3": ["BBG Code 3"],
        "underlying_4": ["BBG Code 4"],
        "underlying_5": ["BBG Code 5"],
        "strike": ["Strike (%)", "Strike %", "Strike"],
        "barrier_type": ["Barrier Type"],
        "barrier": ["KI Barrier (%)", "Barrier (%)"],
        "autocall_frequency": ["Early Termination Period"],
        "no_call_period": ["Non Autocallable Period", "Non Callable Period"],
        "autocall_barrier": ["Early Termination Level (%)"],
        "coupon": [
            "Coupon p.a. (%)",
            "Coupon (%)",
            "Coupon",
            "Exit Rate p.a. (%)",
            "Exit Rate (%)",
            "Exit rate (%)",
        ],
        "reoffer": ["Reoffer (%)", "Reoffer"],
    }

    # --- Build the effective rename_map dynamically ---
    rename_map = {}
    for target, variants in rename_options.items():
        for v in variants:
            if v in df.columns:
                rename_map[v] = target
                break  # stop after the first match

    # --- Rename ---
    df = df.rename(columns=rename_map)

    # --- Clean barrier values (set 0.00 or 0 to NA) ---
    if "barrier" in df.columns:
        # Convert to numeric first (handles "0%", "70%", etc.)
        df["barrier"] = (
            df["barrier"]
            .astype(str)
            .str.replace("%", "", regex=False)
            .str.replace(",", ".", regex=False)
        )
        df["barrier"] = pd.to_numeric(df["barrier"], errors="coerce")
        df.loc[df["barrier"].isin([0, 0.0]), "barrier"] = pd.NA

    return df

def normalize_lukb(df):
    df = df.copy()

    rename_map = {
        "Product": "product",
        "Wrapper": "wrapper",
        "Currency": "currency",
        "Size": "notional",
        "Tenor (m)": "tenor",
        "BBG Code 1": "underlying_1",
        "BBG Code 2": "underlying_2",
        "BBG Code 3": "underlying_3",
        "BBG Code 4": "underlying_4",
        "BBG Code 5": "underlying_5",
        "Settlement": "settlement",
        "Strike (%)": "strike",
        "Strike Type": "strike_type",
        "Barrier Type": "barrier_type",
        "KI Barrier (%)": "barrier",
        "Early Termination Period": "autocall_frequency",
        "Non Callable Period": "no_call_period",
        "Early Termination Level (%)": "autocall_barrier",
        "Early Termination StepUp/Down (%)": "stepupdown",
        "Coupon p.a. (%)": "coupon",
        "Trigger Level (%)": "trigger_level",
        "Memory Coupon": "memory_coupon",
        "Reoffer (%)": "reoffer",
    }

    df = df.rename(columns=rename_map)

    # --- Adjust reoffer: remove Swiss 8% tax uplift ---
    if "reoffer" in df.columns:
        df["reoffer"] = pd.to_numeric(df["reoffer"], errors="coerce")
        mask = df["reoffer"].notna()
        df.loc[mask, "reoffer"] = 100 - (100 - df.loc[mask, "reoffer"]) / 1.08

    # --- Clean barrier values (set 0.00 or 0 to NA) ---
    if "barrier" in df.columns:
        df["barrier"] = pd.to_numeric(df["barrier"], errors="coerce")
        df.loc[df["barrier"].isin([0, 0.0]), "barrier"] = pd.NA

    return df

def normalize_jb(df):
    df = df.copy()
    # --- Define possible variants per logical column ---
    rename_options = {
        "product": ["Product"],
        "wrapper": ["Wrapper"],
        "currency": ["Currency"],
        "tenor": ["Tenor (m)", "Tenor (M)", "Tenor"],
        "underlying_1": ["BBG Code 1"],
        "underlying_2": ["BBG Code 2"],
        "underlying_3": ["BBG Code 3"],
        "underlying_4": ["BBG Code 4"],
        "underlying_5": ["BBG Code 5"],
        "strike": ["Strike (%)"],
        "barrier_type": ["Barrier Type"],
        "barrier": ["KI Barrier (%)"],
        "autocall_frequency": ["Callable Period", "Early Termination Period"],
        "no_call_period": ["Non Callable Period", "Non Autocallable Period"],
        "coupon": ["Coupon p.a. (%)"],
        "reoffer": ["Reoffer (%)", "Upfront (%)"],
        "notional": ["Notional"],
    }

    # --- Dynamic rename ---
    rename_map = {}
    for target, variants in rename_options.items():
        for variant in variants:
            if variant in df.columns:
                rename_map[variant] = target
                break
    df = df.rename(columns=rename_map)
    #print no call period values
    if "no_call_period" in df.columns:
        print("[JB] no_call_period values before cleanup:", df["no_call_period"].unique())

    # --- Julius Baer BBG code cleanup ---
    bbg_map = {"1321 JT": "NKY", "NKY Index": "NKY"}
    for col in [c for c in df.columns if c.startswith("underlying_")]:
        df[col] = df[col].replace(bbg_map)

    # --- Numeric cleanup ---
    for col in ["coupon", "strike", "barrier", "reoffer"]:
        df[col] = (
            df[col]
            .astype(str)
            .str.replace("%", "", regex=False)
            .str.replace(",", ".", regex=False)
        )
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # --- (10.10) Adjusted logic for JB Non-Callable Periods ---
    # Julius Baer expresses "Non Callable Period" as the number of skipped *autocall months*,
    # not as months until the first call like BofA.
    # Example: Monthly autocall, tenor 6 m, Non Callable Period = 2 → first call after 2 months,
    # so 2 full monthly periods are skipped (output = 2).
    if "no_call_period" in df.columns:
        df["no_call_period"] = pd.to_numeric(df["no_call_period"], errors="coerce")
        # Keep the raw number (interpreted directly as skipped periods)
        df.loc[df["no_call_period"].notna(), "no_call_period"] = (
            df["no_call_period"].astype("Int64")
        )

    # --- Reoffer conversion ---
    df.loc[df["reoffer"] <= 20, "reoffer"] = 100 - df["reoffer"]

    # --- Barrier type normalization ---
    if "barrier_type" in df.columns:
        df["barrier_type"] = (
            df["barrier_type"]
            .astype(str)
            .replace({"Continuous": "American", "At Expiry": "European"})
        )

    return df

def normalize_hsbc(df):
    df = df.copy()

    # --- Define possible variants per logical column ---
    rename_options = {
        "product": ["Product"],
        "wrapper": ["Wrapper"],
        "currency": ["Currency"],
        "tenor": ["Tenor (m)", "Tenor", "Tenor (months)", "Tenor m"],
        "underlying_1": ["Underlying", "BBG Code 1", "Underlying 1", "Underlying_1"],
        "underlying_2": ["Und_2", "BBG Code 2", "Underlying 2", "Underlying_2"],
        "underlying_3": ["Und_3", "BBG Code 3", "Underlying 3", "Underlying_3"],
        "underlying_4": ["Und_4", "BBG Code 4", "Underlying 4", "Underlying_4"],
        "underlying_5": ["Und_5", "BBG Code 5", "Underlying 5", "Underlying_5"],
        "strike": ["Strike (%)", "Strike %", "Strike"],
        "barrier_type": ["Barrier Type", "KI Type"],
        "barrier": ["KI Barrier (%)", "Barrier (%)"],
        "autocall_frequency": ["Early Termination Period", "Autocall Frequency"],
        "no_call_period": ["Non Autocallable Period", "No Call Period"],
        "coupon": ["Coupon p.a. (%)", "Coupon (%)", "Coupon"],
        "reoffer": ["Reoffer (%)", "Reoffer", "Reoffer Price"],
        "notional": ["Notional (Ccy)", "Notional", "Nominal (Ccy)"],
        "autocall_barrier": ["Early Termination Level (%)", "Autocall Level (%)"],
        "stepupdown": ["Early Termination StepUp/Down (%)", "Step Up/Down (%)"],
        "trigger_level": ["Trigger Level (%)"],
        "memory_coupon": ["Memory coupon", "Memory Coupon"],
        "id": ["ID"],
        "comment": ["Comment/Remarks", "Comment", "Remarks"],
        "errors": ["Errors", "Error"]
    }

    # --- Rename columns based on the first match found ---
    rename_map = {}
    for target, variants in rename_options.items():
        for variant in variants:
            if variant in df.columns:
                rename_map[variant] = target
                break
    df = df.rename(columns=rename_map)


    return df

def normalize_ms(df):
    df = df.copy()

    # --- Define possible variants per logical column ---
    rename_options = {
        "product": ["Product", "Product Type", "Prod", "Structure"],
        "wrapper": ["Wrapper", "Format", "Instrument Type"],
        "currency": ["CCY", "Currency", "Ccy", "Curr"],
        "notional": ["Notional", "Size", "Trade Size", "Nominal", "Amount", "Issue Size"],
        "reoffer": ["Reoffer (%)", "Reoffer", "Note Price", "Issue Price", "Price (%)"],
        "tenor": ["Tenor (M)", "Tenor (m)", "Tenor", "TENOR", "Maturity", "Tenor (Months)", "Tenor (months)"],
        "underlying_1": ["BBG Code 1", "BBG Code 1 +", "Underlying 1", "UL 1", "Ticker 1"],
        "underlying_2": ["BBG Code 2", "Underlying 2", "UL 2", "Ticker 2"],
        "underlying_3": ["BBG Code 3", "Underlying 3", "UL 3", "Ticker 3"],
        "underlying_4": ["BBG Code 4", "Underlying 4", "UL 4", "Ticker 4"],
        "underlying_5": ["BBG Code 5", "Underlying 5", "UL 5", "Ticker 5"],
        "call_strike": ["Call Strike (%)", "Call Strike %", "Call Strike"],
        "put_strike": ["Put Strike (%)", "Put Strike %", "Put Strike"],
        "strike": ["Strike (%)", "Strike %", "Strike", "Initial Strike (%)"],
        "barrier": ["KI Barrier (%)", "Barrier (%)", "Put Barrier (%)", "Downside Barrier (%)", "Protection (%)"],
        "barrier_type": ["Barrier Type", "Downside Type", "Protection Type", "Barrier Observation Type"],
        "autocall_frequency": ["Early Termination Period", "Coupon Frequency", "Frequency", "Payment Frequency"],
        "autocall_barrier": [
            "Early Termination Level (%)",
            "Autocall Level (%)",
            "Autocall Trigger Level (%)",
            "Trigger Level (%)",
            "Autocall (%)"
        ],
        "stepupdown": ["Early Termination StepUp/Down (%)", "Step-Up/Down", "Step Up/Down (%)"],
        "no_call_period": [
            "Autocall from Period X",
            "Non Autocallable Period",
            "Autocall Protection (Months)",
            "NoCall Period",
            "Non-Callable Period"
        ],
        "trigger_level": ["Trigger Level (%)", "Autocall Trigger Level (%)", "Autocall Barrier (%)"],
        "coupon_periodic": ["Periodic Coupon (%)", "Coupon Periodic (%)", "Coupon per Period (%)"],
        "coupon": [
            "Coupon Per Annum (%)",
            "Coupon p.a. (%)",
            "Coupon (%)",
            "Coupon",
            "Coupon Rate (%)",
            "Coupon p.a.",
            "Coupon p.a",
        ],
        "memory_coupon": ["Memory coupon", "Memory Coupon", "Memory", "Coupon Memory", "Has Memory"],
        "participation": ["Participation (%)", "Participation Rate (%)", "Part (%)"],
        "cap": ["Cap Value (%)", "Cap (%)", "Cap Level (%)"],
        "digital_strike": ["Digital Strike (%)", "Digital Level (%)"],
        "issue_date": ["Issue Date", "Issue Date (T + business days)", "Valuta Date", "Settlement Date"],
        "strike_date": ["Strike Date", "Fixing Date", "Initial Fixing Date"],
    }

    # --- Build rename map dynamically ---
    rename_map = {}
    for target, variants in rename_options.items():
        for v in variants:
            if v in df.columns:
                rename_map[v] = target
                break  # stop after first match

    df = df.rename(columns=rename_map)

    # --- Combine Call/Put Strike into one Strike ---
    # --- Combine Call/Put Strike into one Strike ---
    if "call_strike" in df.columns or "put_strike" in df.columns:
        call = pd.to_numeric(df.get("call_strike", pd.NA).astype(str).str.replace("%", ""), errors="coerce")
        put = pd.to_numeric(df.get("put_strike", pd.NA).astype(str).str.replace("%", ""), errors="coerce")

        strike = pd.Series(np.nan, index=df.index, dtype=float)

        both = call.notna() & put.notna()
        strike[both & (call != 100) & (put == 100)] = call[both & (call != 100) & (put == 100)]
        strike[both & (put != 100) & (call == 100)] = put[both & (put != 100) & (call == 100)]
        strike[both & (call != 100) & (put != 100)] = call[both & (call != 100) & (put != 100)]
        strike[both & (call == 100) & (put == 100)] = 100

        strike[call.notna() & put.isna()] = call[call.notna() & put.isna()]
        strike[put.notna() & call.isna()] = put[put.notna() & call.isna()]

        df["strike"] = strike
        df = df.drop(columns=[c for c in ["call_strike", "put_strike"] if c in df.columns])

    # --- Convert numeric columns ---
    for col in ["reoffer", "strike", "barrier", "autocall_barrier", "coupon", "coupon_periodic"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace("%", ""), errors="coerce")

    # --- Annualize periodic coupon if needed ---
    if "coupon" not in df.columns and "coupon_periodic" in df.columns:
        if "coupon_frequency" in df.columns:
            freq_map = {"Annual": 1, "Semi-Annual": 2, "Quarterly": 4, "Monthly": 12}
            df["coupon_frequency"] = df["coupon_frequency"].map(freq_map).fillna(
                pd.to_numeric(df["coupon_frequency"], errors="coerce")
            )
            mask = df["coupon_periodic"].notna() & df["coupon_frequency"].notna()
            df.loc[mask, "coupon"] = df.loc[mask, "coupon_periodic"] * df.loc[mask, "coupon_frequency"]

    # --- Standardize no_call_period ---
    if "no_call_period" in df.columns:
        df["no_call_period"] = pd.to_numeric(df["no_call_period"], errors="coerce")
        mask = df["no_call_period"].notna() & (df["no_call_period"] > 0)
        df.loc[mask, "no_call_period"] = df.loc[mask, "no_call_period"] - 1
        df["no_call_period"] = df["no_call_period"].round().astype("Int64")

    # --- Standardize text formats ---
    if "barrier_type" in df.columns:
        df["barrier_type"] = df["barrier_type"].astype(str).str.title()

    if "autocall_frequency" in df.columns:
        freq_map = {
            "1": "Monthly",
            "3": "Quarterly",
            "6": "Semi-Annual",
            "12": "Annual",
            "Quarterly": "Quarterly",
            "Semi-Annual": "Semi-Annual",
            "Annual": "Annual",
            "Monthly": "Monthly"
        }
        df["autocall_frequency"] = df["autocall_frequency"].astype(str).str.title()
        df["autocall_frequency"] = df["autocall_frequency"].map(freq_map).fillna(df["autocall_frequency"])

    # --- Clean underlyings ---
    for col in ["underlying_1", "underlying_2", "underlying_3", "underlying_4", "underlying_5"]:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.strip()
                .str.split(" ", n=1).str[0]
                .str.split(".", n=1).str[0]
                .replace({"": pd.NA, "nan": pd.NA, "NaN": pd.NA, "None": pd.NA})
            )

    return df

def normalize_jpm(df):
    df = df.copy()

    # --- Define column variants per logical field ---
    rename_options = {
        "product": ["Product", "Product Name"],
        "wrapper": ["Wrapper", "Product Type", "Format"],
        "currency": ["Currency", "Ccy"],
        "tenor": ["Tenor (m)", "Tenor", "Tenor (months)", "Maturity", "Tenor (M)"],
        "underlying_1": ["BBG Code 1", "Underlying 1"],
        "underlying_2": ["BBG Code 2", "Underlying 2"],
        "underlying_3": ["BBG Code 3", "Underlying 3"],
        "underlying_4": ["BBG Code 4", "Underlying 4"],
        "underlying_5": ["BBG Code 5", "Underlying 5"],
        "strike": ["Strike (%)", "Strike %", "Strike"],
        "barrier_type": ["Barrier Type", "KI Type", "KI Barrier Type"],
        "barrier": ["KI Barrier (%)", "KI Barrier Level (%)", "Barrier (%)"],
        "autocall_frequency": [
            "Early Termination Period",
            "KO Frequency",
            "Autocall Frequency",
            "Observation Frequency",
        ],
        "no_call_period": [
            "Non Autocallable Period",
            "Non Callable Periods",
            "No Call Period",
            "No Call Periods",
            "Non-Callable Period",
        ],
        "autocall_barrier": [
            "Early Termination Level (%)",
            "Autocall Barrier (%)",
            "KO Barrier (%)",
            "Trigger Level (%)",
        ],
        "stepupdown": ["Early Termination StepUp/Down (%)", "Step Up/Down (%)"],
        "coupon_period": ["Coupon Period", "Coupon Frequency", "Payment Frequency"],
        "coupon": ["Coupon p.a. (%)", "Coupon (%)", "Coupon Rate", "Fixed Coupon p.a. (%)"],
        "trigger_level": ["Trigger Level (%)", "Autocall Trigger (%)"],
        "memory_coupon": ["Memory coupon", "Memory Feature", "Coupon Memory"],
        "reoffer": ["Reoffer (%)", "Upfront (%)", "Fees Upfront/PC", "Price Result"],
        "notional": ["Notional", "Nominal", "Issue Size"],
    }

    # --- Build effective rename map dynamically ---
    rename_map = {}
    for target, variants in rename_options.items():
        for variant in variants:
            if variant in df.columns:
                rename_map[variant] = target
                break  # stop after the first match

    # --- Apply rename map ---
    df = df.rename(columns=rename_map)

    # Clean numeric values
    for col in ["coupon", "strike", "barrier", "autocall_barrier", "reoffer"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace("%", ""), errors="coerce")

    # Standardize text case
    if "barrier_type" in df.columns:
        df["barrier_type"] = df["barrier_type"].astype(str).str.title()
    if "autocall_frequency" in df.columns:
        df["autocall_frequency"] = df["autocall_frequency"].astype(str).str.title()

        # For JPM, replace missing underlying placeholders with NaN
    for col in ["underlying_1", "underlying_2", "underlying_3", "underlying_4", "underlying_5"]:
        if col in df.columns:
            df[col] = df[col].replace({"-": pd.NA, "": pd.NA})

    return df   


def normalize_ubs(df):
    df = df.copy()

    # --- Normalize header formatting (handle hidden chars / hyphens) ---
    df.columns = (
        df.columns.astype(str)
        .str.replace("\xa0", " ", regex=False)
        .str.replace("-", " ", regex=False)
        .str.strip()
    )

    # --- Define possible variants per logical column ---
    rename_options = {
        "product": ["Product"],
        "currency": ["Currency"],
        "underlying_1": ["Underlying 1"],
        "underlying_2": ["Underlying 2"],
        "underlying_3": ["Underlying 3"],
        "underlying_4": ["Underlying 4"],
        "underlying_5": ["Underlying 5"],
        "reoffer": ["Reoffer (%)", "Upfront (%)"],
        "tenor": ["Tenor (m)", "Tenor", "Tenor (M)"],
        "autocall_frequency": ["Frequency"],
        "no_call_period": [
            "Autocall From Period",
            "Callable by issuer from Period",  # <-- added key UBS variant
            "Non Autocallable Period",
            "No Call Period",
            "Non Callable Period",
        ],
        "autocall_barrier": ["Autocall Level (%)"],
        "coupon": ["Coupon p.a. (%)", "Coupon (%)"],
        "barrier_type": ["Barrier Type", "KI Barrier Type"],
        "barrier": ["Barrier (%)", "KI Barrier (%)"],
        "strike": ["Put Strike (%)", "Strike (%)"],
    }

    # --- Build rename map dynamically ---
    rename_map = {}
    for target, variants in rename_options.items():
        for variant in variants:
            if variant in df.columns:
                rename_map[variant] = target
                break

    df = df.rename(columns=rename_map)

    # --- Numeric cleanup ---
    for col in ["coupon", "strike", "barrier", "autocall_barrier", "reoffer"]:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace("%", "", regex=False)
                .str.replace(",", ".", regex=False)
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # --- Tenor cleanup ---
    if "tenor" in df.columns:
        df["tenor"] = pd.to_numeric(
            df["tenor"].astype(str).str.replace("m", "", case=False, regex=False),
            errors="coerce",
        )

    # --- UBS 'Callable by issuer from Period' logic ---
    # (10.10) UBS defines "Callable by issuer from Period" as the *first callable month*,
    # not the count of fully non-callable periods.
    # Example: Monthly autocall, tenor 6m, "Callable by issuer from Period" = 3
    # → first call at month 3 ⇒ 2 full periods skipped (output must be 2).
    if "no_call_period" in df.columns:
        df["no_call_period"] = pd.to_numeric(df["no_call_period"], errors="coerce")
        mask = df["no_call_period"].notna() & (df["no_call_period"] > 0)
        df.loc[mask, "no_call_period"] = df.loc[mask, "no_call_period"] - 1
        df["no_call_period"] = df["no_call_period"].round().astype("Int64")

    # --- Clean underlyings ---
    for col in ["underlying_1", "underlying_2", "underlying_3", "underlying_4", "underlying_5"]:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.strip()
                .str.replace(" Equity", "", regex=False)
                .str.replace(r"\.[A-Z]$", "", regex=True)  # remove .N, .OQ, etc.
                .replace({"nan": pd.NA, "None": pd.NA, "": pd.NA})
            )

    return df


def normalize_marex(df):
    df = df.copy()
    rename_map = {
        "Structure": "product",
        "Currency": "currency",
        "Bloomberg Ticker 1": "underlying_1",
        "Bloomberg Ticker 2": "underlying_2",
        "Bloomberg Ticker 3": "underlying_3",
        "Bloomberg Ticker 4": "underlying_4",
        "Bloomberg Ticker 5": "underlying_5",
        "Bloomberg Ticker 6": "underlying_6",   # optional, not in core schema
        "Reoffer / Upfront (%)": "reoffer",
        "Tenor (m)": "tenor",
        "Frequency": "autocall_frequency",
        "First Observation in (m)": "no_call_period",
        "Autocall Trigger Level (%)": "autocall_barrier",
        "Coupon p.a. (%)": "coupon",
        "Strike Level (%)": "strike",
        "Barrier Type": "barrier_type",
        "Barrier Level": "barrier",
    }
    df = df.rename(columns=rename_map)

    # Clean numeric fields
    for col in ["coupon", "strike", "barrier", "autocall_barrier", "reoffer"]:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace("%", "", regex=False)
                .str.replace(",", ".", regex=False)
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "tenor" in df.columns:
        df["tenor"] = (
            df["tenor"].astype(str).str.replace("m", "", case=False, regex=False)
        )
        df["tenor"] = pd.to_numeric(df["tenor"], errors="coerce")

    if "autocall_frequency" in df.columns and "no_call_period" in df.columns:
        # map frequency to months
        freq_map = {"Monthly": 1, "Quarterly": 3, "Semi-Annual": 6, "Annual": 12}
        df["freq_months"] = df["autocall_frequency"].map(freq_map)

        # compute no_call_period = (first_obs / freq_months) - 1
        df["no_call_period"] = pd.to_numeric(df["no_call_period"], errors="coerce")
        df["no_call_period"] = (
            (df["no_call_period"] / df["freq_months"]).fillna(0).astype(int) - 1
        ).clip(lower=0)

        df = df.drop(columns=["freq_months"])
    return df


import pandas as pd

def normalize_bbva(df):
    df = df.copy()

    # --- Define possible variants per logical column ---
    rename_options = {
        "product": ["Product"],
        "currency": ["Currency"],
        "tenor": ["Expiry / Maturity / Tenor", "Tenor", "Tenor (m)", "Tenor (months)"],
        "underlying_1": ["BBG Code 1"],
        "underlying_2": ["BBG Code 2"],
        "underlying_3": ["BBG Code 3"],
        "underlying_4": ["BBG Code 4"],
        "underlying_5": ["BBG Code 5"],
        "strike": ["Strike (%)", "Strike (%)*", "Strike"],
        "barrier_type": ["Barrier Type", "KI Type", "KI Barrier Type"],
        "barrier": ["KI Barrier Level (%)", "KI Barrier (%)", "Barrier (%)"],
        "autocall_frequency": [
            "Frequency (1m, 3m, 6m, 12m)",
            "ER Frequency (1m, 3m, 6m, 12m)",
        ],
        "no_call_period": ["ER Non cancelable Periods", "NC Periods"],
        "autocall_barrier": [
            "Autocall Trigger Level (%)",
            "ER Trigger (%)",
            "ER Coupon Type",
        ],
        "coupon": [
            "Coupon (%)",
            "Coupon (%)*",
            "Coupon p.a. (%)",
            "ER Coupon Amount (%)"
        ],
        "reoffer": ["Price Result", "Reoffer (%)"],
    }

    # --- Build effective rename map dynamically ---
    rename_map = {}
    for target, variants in rename_options.items():
        for v in variants:
            if v in df.columns:
                rename_map[v] = target
                break  # first found variant

    # --- Rename columns ---
    df = df.rename(columns=rename_map)

    # --- Numeric cleanup ---
    for col in ["coupon", "strike", "barrier", "autocall_barrier", "reoffer"]:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace("%", "", regex=False)
                .str.replace(",", ".", regex=False)
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # --- Tenor cleanup ---
    if "tenor" in df.columns:
        df["tenor"] = (
            df["tenor"].astype(str)
            .str.replace("m", "", case=False, regex=False)
            .str.replace("M", "", case=False, regex=False)
        )
        df["tenor"] = pd.to_numeric(df["tenor"], errors="coerce")

    # --- Normalize frequency ---
    freq_map = {
        "1M": "Monthly",
        "3M": "Quarterly",
        "6M": "Semi-Annual",
        "12M": "Annual"
    }
    if "autocall_frequency" in df.columns:
        df["autocall_frequency"] = df["autocall_frequency"].astype(str).replace(freq_map, regex=False)

    # --- Annualize coupon depending on frequency ---
    if "coupon" in df.columns and "autocall_frequency" in df.columns:
        annual_factors = {
            "Monthly": 12,
            "Quarterly": 4,
            "Semi-Annual": 2,
            "Annual": 1,
        }
        df["coupon"] = df.apply(
            lambda row: row["coupon"] * annual_factors.get(row["autocall_frequency"], 1)
            if pd.notna(row["coupon"]) else row["coupon"],
            axis=1
        )

    # --- Normalize barrier type ---
    if "barrier_type" in df.columns:
        df["barrier_type"] = df["barrier_type"].replace({
            "At Expiry": "European",
            "American Continuous": "American"
        })

    return df

def normalize_cibc(df):
    df = df.copy()
    rename_map = {
        "Client Ref": "product",
        "Pricing Ccy": "currency",
        "Term": "tenor",
        "Price": "reoffer",   # price quoted as %
        "Coupon per Period": "coupon",
        "Principal Barrier": "barrier",
        "Underlying(s)": "underlyings",
        "Barrier Monitoring": "barrier_type",
        "Auto-Call Barrier": "autocall_barrier",
        "Auto-Call Freq": "autocall_frequency",
        "Auto-Call Start": "auto_call_start",
        "Callable": "callable_flag",   # True/False
        "Put Strike": "strike",
    }
    df = df.rename(columns=rename_map)

    df["issuer"] = "CIBC"

    # ---- tenor cleanup (e.g. 12M -> 12)
    if "tenor" in df.columns:
        df["tenor"] = df["tenor"].astype(str).str.replace("M", "", regex=False)
        df["tenor"] = pd.to_numeric(df["tenor"], errors="coerce")

    # ---- handle underlyings
    if "underlyings" in df.columns:
        split_cols = df["underlyings"].astype(str).str.split(r"[;,]", expand=True)
        for i in range(5 - split_cols.shape[1]):
            split_cols[split_cols.shape[1] + i] = None
        split_cols = split_cols.iloc[:, :5]
        split_cols = split_cols.apply(
            lambda col: col.str.strip().str.replace(" Equity", "", regex=False)
            if col.dtype == "object" else col
        )
        df[["underlying_1", "underlying_2", "underlying_3",
            "underlying_4", "underlying_5"]] = split_cols
        df = df.drop(columns=["underlyings"])

    # ---- no_call_period logic
    freq_map = {"Quarterly": 3, "Semi-Annual": 6, "Annual": 12}
    freq_months = df["autocall_frequency"].map(freq_map)

    if "auto_call_start" in df.columns:
        auto_start = (
            df["auto_call_start"]
            .astype(str)
            .str.replace("M", "", regex=False)
            .replace("nan", "")
        )
        auto_start = pd.to_numeric(auto_start, errors="coerce")

        # formula: (start / freq) - 1
        df["no_call_period"] = auto_start.divide(freq_months) - 1
        df["no_call_period"] = df["no_call_period"].where(df["no_call_period"] >= 0)
        df["no_call_period"] = df["no_call_period"].astype("Int64")  # allows NaN
    else:
        df["no_call_period"] = pd.NA


    # ---- numeric cleanup
    for col in ["coupon", "strike", "barrier", "reoffer", "autocall_barrier"]:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace("%", "", regex=False)
                .str.replace(",", ".", regex=False)
            )
            if col != "autocall_barrier":
                df[col] = pd.to_numeric(df[col], errors="coerce")
                
        return df

def normalize_barclays(df):
    df = df.copy()
    rename_map = {
        "Product": "product",
        "Coupon p.a. (%)": "coupon",
        "Tenor (m)": "tenor",
        "Strike (%)": "strike",
        "KI Barrier (%)": "barrier",
        "Reoffer (%)": "reoffer",
        "Currency": "currency",
        "BBG Code 1": "underlying_1",
        "BBG Code 2": "underlying_2",
        "BBG Code 3": "underlying_3",
        "BBG Code 4": "underlying_4",
        "Barrier Type": "barrier_type",
        "Early Termination Period": "autocall_frequency",
        "Non Autocallable Period": "no_call_period",
        "Early Termination Level (%)": "autocall_barrier",
    }
    df = df.rename(columns=rename_map)

    numeric_cols = ["coupon", "tenor", "strike", "barrier", "reoffer", "autocall_barrier"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace("%", "", regex=False)
                .str.replace(",", ".", regex=False)
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # --- Underlying cleanup ---
    for col in ["underlying_1", "underlying_2", "underlying_3", "underlying_4"]:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace(" Equity", "", regex=False)
                .str.replace(r"\s(SE|SW|FP|GY|UN)$", "", regex=True)  # drop suffixes
                .replace({"nan": pd.NA, "None": pd.NA})
            )

    return df


def normalize_leonteq(df):
    df = df.copy()
    rename_options = {
        "product": ["Product"],
        "currency": ["Currency"],
        "issuer": ["Issuer", "Emittent"],
        "underlying_1": ["BBG Code 1"],
        "underlying_2": ["BBG Code 2"],
        "underlying_3": ["BBG Code 3"],
        "underlying_4": ["BBG Code 4"],
        "strike": ["Strike (%)", "Put Strike (%)", "Strike %"],
        "tenor": ["Tenor (m)", "Tenor (months)", "Maturity (m)", "Maturity (months)"],
        "coupon": ["Coupon p.a. (%)", "Coupon (%)", "Coupon Rate (%)", "Coupon %"],
        "reoffer": ["Upfront / NotePrice (%)", "Reoffer (%)", "Price (%)", "Note Price (%)"],
        "barrier_type": ["Barrier Type"],
        "barrier": ["KI Barrier (%)", "KI Barrier", "KI Barrier Level (%)", "Barrier (%)"],
        "autocall_barrier": ["KO Barrier (%)", "Autocall Trigger (%)", "Autocall Level (%)"],
        "autocall_frequency": ["Observation Frequency (m)", "Callable Frequency (m)", "Call Frequency (m)"],
        "no_call_period": ["Non Callable Periods", "Non-Callable Periods", "No Call Periods"],
    }

    # --- Build effective rename map dynamically ---
    rename_map = {
        v: target
        for target, variants in rename_options.items()
        for v in variants if v in df.columns
    }

    # --- Rename columns ---
    df = df.rename(columns=rename_map)


    # --- Clean numeric values
    for col in ["coupon", "tenor", "strike", "barrier", "reoffer", "autocall_barrier", "autocall_frequency"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # --- Clean underlyings
    for col in ["underlying_1", "underlying_2", "underlying_3", "underlying_4"]:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.strip()
                .str.replace(" Equity", "", regex=False)   # drop "Equity"
                .str.replace(r"\s+[A-Z]{2}$", "", regex=True)  # drop country codes (FP, GY, UN…)
                .replace({"nan": pd.NA, "None": pd.NA, "NaN": pd.NA})
            )

    # --- Convert autocall_frequency months → label
    if "autocall_frequency" in df.columns:
        freq_map = {1: "Monthly", 3: "Quarterly", 6: "Semi-Annual", 12: "Annual"}
        df["autocall_frequency"] = df["autocall_frequency"].map(freq_map).fillna(df["autocall_frequency"])

    if "barrier_type" in df.columns:
        df["barrier_type"] = (
            df["barrier_type"]
            .astype(str)
            .replace({"Continuous": "American"})  # Leonteq wording
            .str.title()
        )

    return df
    
def normalize_swissquote(df):
    df = df.copy()
    rename_map = {
        "Product Type": "product",
        "Currency": "currency",
        "Size": "notional",
        "Distribution Fee (%)": "reoffer",  # fee
        "Maturity": "tenor",
        "Stock identifier 1": "underlying_1",
        "Stock identifier 2": "underlying_2",
        "Stock identifier 3": "underlying_3",
        "Stock identifier 4": "underlying_4",
        "Stock identifier 5": "underlying_5",
        "Coupon Rate (%)": "coupon",
        "Coupon Type": "coupon_type",
        "Coupon Trigger level": "coupon_trigger",
        "Memory": "memory_coupon",
        "Strike (%)": "strike",
        "Barrier?": "barrier_flag",
        "Barrier level (%)": "barrier",
        "Barrier Type": "barrier_type",
        "Mechanism": "mechanism",
        "Frequency": "autocall_frequency",
        "First Observation": "no_call_period",
        "Autocall Trigger level": "autocall_barrier"
    }
    df.rename(columns=rename_map, inplace=True)

    # --- Coupon ---
    if "coupon" in df.columns:
        df["coupon"] = (
            df["coupon"]
            .astype(str)
            .str.extract(r"([\d\.,]+)")[0]
            .str.replace(",", ".", regex=False)
        )
        df["coupon"] = pd.to_numeric(df["coupon"], errors="coerce")

    # --- Reoffer = 100 - Distribution Fee ---
    if "reoffer" in df.columns:
        fee = pd.to_numeric(df["reoffer"], errors="coerce")
        df["reoffer"] = 100 - fee

   # --- Tenor: convert mixed strings like 1Y6M → 18, 2Y3M → 27, 6M → 6, 1Y → 12 ---
    def parse_tenor(x):
        if pd.isna(x):
            return pd.NA
        s = str(x).strip().upper()
        if not s:
            return pd.NA
        # Match both year and month parts
        match = re.match(r"(?:(\d+)\s*Y)?\s*(?:(\d+)\s*M)?", s)
        if match:
            years = int(match.group(1)) if match.group(1) else 0
            months = int(match.group(2)) if match.group(2) else 0
            total = years * 12 + months
            return total if total > 0 else pd.NA
        return pd.NA

    if "tenor" in df.columns:
        df["tenor"] = df["tenor"].map(parse_tenor)

    # --- no_call_period: compute periods from first obs / freq ---
    if "autocall_frequency" in df.columns and "no_call_period" in df.columns:
        freq_map = {"Monthly": 1, "Quarterly": 3, "Semi-Annual": 6, "Annual": 12}
        freq_months = df["autocall_frequency"].map(freq_map)

        df["no_call_period"] = (
            df["no_call_period"].astype(str)
            .str.replace("M", "", regex=False)
            .str.replace("Y", "*12", regex=False)
        )
        df["no_call_period"] = df["no_call_period"].apply(
            lambda x: eval(x) if isinstance(x, str) and "*" in x else x
        )
        df["no_call_period"] = pd.to_numeric(df["no_call_period"], errors="coerce")

        mask = df["no_call_period"].notna() & freq_months.notna()
        df.loc[mask, "no_call_period"] = (
            df.loc[mask, "no_call_period"] / freq_months[mask]
        ) - 1
        df["no_call_period"] = df["no_call_period"].clip(lower=0).astype("Int64")

    # --- Clean underlyings: keep only ticker root before first space ---
    for col in ["underlying_1", "underlying_2", "underlying_3", "underlying_4", "underlying_5"]:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.strip()
                .str.split(" ", n=1).str[0]   # keep part before first space
                .replace({"": pd.NA, "nan": pd.NA, "NaN": pd.NA, "None": pd.NA})
            )

    return df