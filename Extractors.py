
from bs4 import BeautifulSoup
import pandas as pd
import re
# =========================
# Extractor for Natixis
# =========================
def extract_natixis(html: str) -> pd.DataFrame | None:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None

    target_table = tables[0]  # Natixis: first table only
    rows = []
    for tr in target_table.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)

    if len(rows) <= 1:
        return None
    
    rows = normalize_html_rows(rows)

    df = pd.DataFrame(rows[1:], columns=rows[0])
    df.columns = [c.strip().replace("\xa0", " ") for c in df.columns]
    return df

# =========================
# Extractor for Citi
# =========================
def extract_citi(html: str) -> pd.DataFrame | None:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None

    target_table = None
    for t in tables:
        rows = t.find_all("tr")
        if len(rows) > 1:  # header + data
            target_table = t
            break

    if target_table is None:
        return None

    rows = []
    for tr in target_table.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)

    if len(rows) <= 1:
        return None

    df = pd.DataFrame(rows[1:], columns=rows[0])
    df.columns = [c.strip().replace("\xa0", " ") for c in df.columns]
    return df

# =========================
# Extractor for BofA
# =========================
def extract_bofa(html: str) -> pd.DataFrame | None:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None

    target_table = None
    for t in tables:
        rows = t.find_all("tr")
        if len(rows) > 1:
            target_table = t
            break

    if target_table is None:
        return None

    rows = []
    for tr in target_table.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)

    if len(rows) <= 1:
        return None

    rows = normalize_html_rows(rows)

    df = pd.DataFrame(rows[1:], columns=rows[0])
    df.columns = [c.strip().replace("\xa0", " ") for c in df.columns]
    return df

# =========================
# Extractor for SocGen
# =========================

def extract_socgen(html: str) -> pd.DataFrame | None:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None

    target_table = None
    for t in tables:
        rows = t.find_all("tr")
        if len(rows) > 1:  # header + data
            target_table = t
            break

    if target_table is None:
        return None

    rows = []
    for tr in target_table.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)

    if len(rows) <= 1:
        return None

    rows = normalize_html_rows(rows)

    df = pd.DataFrame(rows[1:], columns=rows[0])
    df.columns = [c.strip().replace("\xa0", " ") for c in df.columns]
    return df

# =========================
# Extractor for Goldman Sachs
# =========================

def extract_gs(html: str) -> pd.DataFrame | None:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None

    # pick table with Product + Currency headers
    target_table = None
    for t in tables:
        headers = [th.get_text(" ", strip=True) for th in t.find_all("th")]
        if "Product" in headers and "Currency" in headers:
            target_table = t
            break
    if target_table is None:
        return None

    rows = []
    for tr in target_table.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)

    if len(rows) <= 1:
        return None
    
    rows = normalize_html_rows(rows)

    df = pd.DataFrame(rows[1:], columns=rows[0])
    df.columns = [c.strip().replace("\xa0", " ") for c in df.columns]
    return df

# =========================
# Extractor for BNP Paribas
# =========================
def extract_bnp(html: str) -> pd.DataFrame | None:


    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None

    target_table = None
    for t in tables:
        rows = t.find_all("tr")
        if len(rows) > 1:
            headers = [td.get_text(" ", strip=True) for td in rows[0].find_all(["td", "th"])]
            if any(any(k in h for k in ["Coupon", "Exit Rate"]) for h in headers):
                target_table = t
                break  # stop at first match

    if target_table is None:
        return None

    rows = []
    for tr in target_table.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)

    if len(rows) <= 1:
        return None
    
    rows = normalize_html_rows(rows)

    df = pd.DataFrame(rows[1:], columns=rows[0])
    df.columns = (
        df.columns
        .str.strip()
        .str.replace("\xa0", " ", regex=False)
        .str.replace(r"\s+", " ", regex=True)
    )

    return df


# =========================
# Extractor for LUKB
# =========================

def extract_lukb(html: str) -> pd.DataFrame | None:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None

    # always take the FIRST table
    target_table = tables[0]

    # Try pandas first (works when lxml/html5lib installed), otherwise fall back to manual scraping
    try:
        dfs = pd.read_html(str(target_table)) or []
    except Exception:
        dfs = []

    if dfs:
        df = dfs[0]
        # If header row ended up as first data row (common for Word HTML), promote it
        try:
            cols_clean = [str(c).strip().replace("\xa0", " ").replace("\n", " ") for c in df.columns]
            # Heuristic: if numeric/range-like column names or generic 0..N, and first row contains expected labels
            first_row = [str(x).strip() for x in df.iloc[0].tolist()]
            if any(k in " ".join(first_row) for k in ["Product", "Wrapper", "Currency", "Tenor (m)"]):
                df = df[1:]
                df.columns = [re.sub(r"\s+", " ", s) for s in first_row]
            else:
                df.columns = cols_clean
        except Exception:
            df.columns = [str(c).strip().replace("\xa0", " ").replace("\n", " ") for c in df.columns]
        return df

    # Manual BeautifulSoup parse
    rows = []
    for tr in target_table.find_all("tr"):
        cells = [td.get_text(" ", strip=True).replace("\n", " ") for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)

    if len(rows) <= 1:
        return None

    rows = normalize_html_rows(rows)

    # first row is header
    try:
        df = pd.DataFrame(rows[1:], columns=rows[0])
    except Exception:
        df = pd.DataFrame(rows)

    df.columns = [c.strip().replace("\xa0", " ").replace("\n", " ") for c in df.columns]
    return df

# =========================
# Extractor for JB
# =========================

def extract_jb(html: str) -> pd.DataFrame | None:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None

    # JB has one main table
    target_table = tables[0]

    rows = []
    for tr in target_table.find_all("tr"):
        cells = [td.get_text(" ", strip=True).replace("\n", " ") for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)

    if len(rows) <= 1:
        return None
    
    rows = normalize_html_rows(rows)

    df = pd.DataFrame(rows[1:], columns=rows[0])
    df.columns = [c.strip().replace("\xa0", " ").replace("\n", " ") for c in df.columns]

    return df

# =========================
# Extractor for HSBC
# =========================

def extract_hsbc(html: str) -> pd.DataFrame | None:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None

    # HSBC has one main table
    target_table = tables[0]

    rows = []
    for tr in target_table.find_all("tr"):
        cells = [td.get_text(" ", strip=True).replace("\n", " ") for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)

    if len(rows) <= 1:
        return None

    rows = normalize_html_rows(rows)

    df = pd.DataFrame(rows[1:], columns=rows[0])
    df.columns = [c.strip().replace("\xa0", " ").replace("\n", " ") for c in df.columns]
    
    return df

# =========================
# Extractor for Morgan Stanley
# =========================

def extract_ms(html: str) -> pd.DataFrame | None:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    def _text_blocks_to_dfs() -> list[pd.DataFrame]:
        """Fallback for plain-text mails rendered without <table> tags."""
        text = soup.get_text("\n", strip=False)
        lines = [ln.strip() for ln in text.splitlines()]
        blocks: list[list[str]] = []
        block: list[str] = []
        for ln in lines:
            if not ln:
                if block:
                    blocks.append(block)
                    block = []
                continue
            block.append(ln)
        if block:
            blocks.append(block)

        frames: list[pd.DataFrame] = []
        for blk in blocks:
            rows: list[list[str]] = []
            for raw in blk:
                parts = [p.strip() for p in re.split(r"\t+|\s{2,}", raw) if p.strip()]
                if parts:
                    rows.append(parts)
            if len(rows) <= 1:
                continue
            max_len = max(len(r) for r in rows)
            normalized = [r + [""] * (max_len - len(r)) for r in rows]
            header = normalized[0]
            data = normalized[1:]
            try:
                frames.append(pd.DataFrame(data, columns=header))
            except Exception:
                continue
        return frames

    def looks_like_ms(df: pd.DataFrame) -> bool:
        # Relaxed heuristics: require a product/structure-like header and at least
        # one of currency/tenor/coupon/size/notional/reoffer/maturity in headers
        try:
            headers = [str(c).strip().lower() for c in df.columns]
        except Exception:
            return False

        header_text = " ".join(headers)
        product_keys = ["product", "structure", "instrument", "security"]
        other_keys = ["currency", "tenor", "coupon", "size", "notional", "reoffer", "maturity"]

        if any(k in header_text for k in product_keys) and any(k in header_text for k in other_keys):
            return True

        # also accept if first column contains field names (transposed tables)
        try:
            first_col_vals = [str(x).strip().lower() for x in df.iloc[:, 0].tolist()] if df.shape[1] > 0 else []
            fc_text = " ".join(first_col_vals)
            if any(k in fc_text for k in other_keys + product_keys):
                return True
        except Exception:
            pass

        return False

    if not tables:
        for df in _text_blocks_to_dfs():
            df.columns = [str(c).strip().replace("\xa0", " ").replace("\n", " ") for c in df.columns]
            if looks_like_ms(df):
                return df
        return None

    for t in tables:
        dfs = []
        # try pandas first
        try:
            dfs = pd.read_html(str(t)) or []
        except Exception:
            # manual fallback: build rows via BeautifulSoup
            rows = []
            for tr in t.find_all("tr"):
                cells = [td.get_text(" ", strip=True).replace("\n", " ") for td in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            if rows:
                if len(rows) >= 2 and all(isinstance(c, str) for c in rows[0]):
                    try:
                        dfs = [pd.DataFrame(rows[1:], columns=rows[0])]
                    except Exception:
                        dfs = [pd.DataFrame(rows)]
                else:
                    dfs = [pd.DataFrame(rows)]

        for df in dfs or []:
            try:
                df.columns = [str(c).strip().replace("\xa0", " ").replace("\n", " ") for c in df.columns]
                if looks_like_ms(df):
                    return df
            except Exception:
                continue

        # Try transpose-style tables (first column = field names)
        df0 = None
        try:
            df0 = pd.read_html(str(t), header=0)[0]
        except Exception:
            # manual transpose attempt
            rows = []
            for tr in t.find_all("tr"):
                cells = [td.get_text(" ", strip=True).replace("\n", " ") for td in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            if rows and len(rows) >= 3 and len(rows[0]) >= 2:
                try:
                    df0 = pd.DataFrame(rows)
                    new_header = df0.iloc[:, 0].tolist()
                    df0 = df0.drop(df0.columns[0], axis=1)
                    df0.columns = new_header
                except Exception:
                    df0 = None

        if df0 is not None:
            try:
                df0.columns = [str(c).strip().replace("\xa0", " ").replace("\n", " ") for c in df0.columns]
                if any(k in " ".join([str(c).lower() for c in df0.columns]) for k in ["currency", "tenor", "coupon", "product", "structure"]):
                    try:
                        dfT = df0.set_index(df0.columns[0]).T.reset_index(drop=True)
                        return dfT
                    except Exception:
                        return df0
            except Exception:
                pass

    # Final fallback: plain-text blocks mixed with HTML tables
    for df in _text_blocks_to_dfs():
        try:
            df.columns = [str(c).strip().replace("\xa0", " ").replace("\n", " ") for c in df.columns]
        except Exception:
            continue
        if looks_like_ms(df):
            return df

    return None

# =========================
# Extractor for JPM
# =========================

def extract_jpm(html):
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None

    # Relaxed header matching: require presence of product, tenor and coupon keywords
    def looks_like_jpm(df: pd.DataFrame) -> bool:
        headers = [str(c).strip().lower() for c in df.columns]
        s = " ".join(headers)
        has_product = any("product" in h for h in headers)
        has_tenor = any("tenor" in h for h in headers)
        has_coupon = any("coupon" in h for h in headers)
        return has_product and has_tenor and has_coupon

    for i, t in enumerate(tables):
        # try pandas first
        dfs = []
        try:
            dfs = pd.read_html(str(t)) or []
        except Exception:
            # manual fallback
            rows = []
            for tr in t.find_all("tr"):
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            if rows and len(rows) > 1:
                try:
                    dfs = [pd.DataFrame(rows[1:], columns=rows[0])]
                except Exception:
                    dfs = [pd.DataFrame(rows)]

        for df in dfs or []:
            try:
                if looks_like_jpm(df):
                    return df
            except Exception:
                continue

    return None

# =========================
# Extractor for UBS
# =========================

def extract_ubs(html: str) -> pd.DataFrame | None:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None
    def looks_like_ubs(df: pd.DataFrame) -> bool:
        headers = [str(c).strip().lower() for c in df.columns]
        # require product + currency + tenor + coupon keywords (substring match)
        return (
            any("product" in h for h in headers)
            and any("currency" in h for h in headers)
            and any("tenor" in h for h in headers)
            and any("coupon" in h for h in headers)
        )

    for i, t in enumerate(tables):
        dfs = []
        try:
            dfs = pd.read_html(str(t)) or []
        except Exception:
            # fallback to manual parse
            rows = []
            for tr in t.find_all("tr"):
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            if rows:
                try:
                    dfs = [pd.DataFrame(rows[1:], columns=rows[0])]
                except Exception:
                    dfs = [pd.DataFrame(rows)]

        for df in dfs or []:
            try:
                if looks_like_ubs(df):
                    return df
            except Exception:
                continue
    return None

# =========================
# Extractor for Marex
# =========================

def extract_marex(html: str) -> pd.DataFrame | None:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        # Plain-text TSV fallback
        text = soup.get_text("\n", strip=True)
        if "\t" in text:
            lines = [ln for ln in text.splitlines() if ln.strip()]
            if len(lines) >= 2:
                headers = [h.strip() for h in lines[0].split("\t")]
                data = [[c.strip() for c in ln.split("\t")] for ln in lines[1:]]
                data = [row + [None] * (len(headers) - len(row)) if len(row) < len(headers) else row[:len(headers)] for row in data]
                try:
                    return pd.DataFrame(data, columns=headers)
                except Exception:
                    pass
        return None

    def looks_like_marex(df: pd.DataFrame) -> bool:
        cols = [str(c).strip().lower() for c in df.columns]
        s = set(cols)
        has_currency = any(c in s for c in {"currency"})
        has_tenor = any(c in s for c in {"tenor (m)", "tenor", "tenor (months)", "maturity"})
        has_coupon = any(c in s for c in {"coupon p.a. (%)", "coupon (%)", "coupon"})
        has_product = any(c in s for c in {"structure", "product"})
        return (has_currency and has_coupon and (has_tenor or has_product)) or (has_currency and has_product)

    for t in tables:
        # Try to parse table with pandas first; if that fails (missing lxml/html5lib),
        # fall back to manual BeautifulSoup parsing into rows and DataFrame.
        dfs = []
        try:
            dfs = pd.read_html(str(t)) or []
        except Exception:
            # Manual parse: collect rows from <tr>, using th/td as cells
            rows = []
            for tr in t.find_all("tr"):
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            if rows:
                # Try to interpret first row as header
                if len(rows) >= 2 and all(isinstance(c, str) for c in rows[0]):
                    try:
                        dfs = [pd.DataFrame(rows[1:], columns=rows[0])]
                    except Exception:
                        dfs = [pd.DataFrame(rows)]
                else:
                    dfs = [pd.DataFrame(rows)]

        for df in dfs or []:
            if looks_like_marex(df):
                return df

        # Transposed-style: first column is field names. Try pandas first, then manual.
        df0 = None
        try:
            df0 = pd.read_html(str(t), header=0)[0]
        except Exception:
            # attempt manual transpose-style parse: promote first column as header
            rows = []
            for tr in t.find_all("tr"):
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            if rows and len(rows) >= 5 and len(rows[0]) >= 2:
                try:
                    df0 = pd.DataFrame(rows)
                    # treat first column as header (column 0 = field names)
                    new_header = df0.iloc[:,0].tolist()
                    df0 = df0.drop(df0.columns[0], axis=1)
                    df0.columns = new_header
                except Exception:
                    df0 = None

        if df0 is not None and df0.shape[0] >= 5 and df0.shape[1] >= 2:
            first_col_vals = set(str(x).strip().lower() for x in df0.iloc[:,0].tolist()) if df0.shape[1] > 0 else set()
            if any(v in first_col_vals for v in ["currency", "tenor", "coupon p.a. (%)", "coupon (%)", "structure", "product"]):
                try:
                    dfT = df0.set_index(df0.columns[0]).T.reset_index(drop=True)
                    return dfT
                except Exception:
                    return df0
    return None


# =========================
# Extractor for BBVA
# =========================
def extract_bbva(html: str) -> pd.DataFrame | None:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None

    for i, t in enumerate(tables):
        # Try pandas HTML parsing first (fast/robust when lxml/html5lib installed)
        raw = None
        try:
            df_list = pd.read_html(str(t), header=0)
            if df_list:
                raw = df_list[0]
        except Exception:
            # Fallback: manually parse table with BeautifulSoup into rows
            rows = []
            for tr in t.find_all("tr"):
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            if len(rows) > 1:
                try:
                    raw = pd.DataFrame(rows[1:], columns=rows[0])
                except Exception:
                    raw = pd.DataFrame(rows)

        if raw is None:
            continue

        # First column = field names (Product, Currency, etc.)
        # Remaining columns = separate products
        if raw.shape[0] < 5 or raw.shape[1] < 2:
            continue

        # transpose into normal orientation
        try:
            df = raw.set_index(raw.columns[0]).T.reset_index(drop=True)
        except Exception:
            df = raw

        return df

    return None

# =========================
# Extractor for CIBC
# =========================

def extract_cibc(html: str) -> pd.DataFrame | None:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None

    for i, t in enumerate(tables):
        try:
            df_list = pd.read_html(str(t), header=0)
        except Exception:
            continue
        if not df_list:
            continue

        df = df_list[0]

        # First row is usually duplicated header row
        if isinstance(df.iloc[0,0], str) and "Client Ref" in df.iloc[0,0]:
            new_header = df.iloc[0]
            df = df[1:]
            df.columns = [str(c).strip() for c in new_header]

        # Normalize columns
        headers = {c.lower().strip() for c in df.columns}

        # CIBC signature columns
        required = {"client ref", "pricing ccy", "notional"}
        if required.issubset(headers):
            return df.reset_index(drop=True)

    return None

# =========================
# Barclays Extractor
# =========================
def extract_barclays(html: str) -> pd.DataFrame | None:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None

    target_table = None
    for t in tables:
        headers = [td.get_text(" ", strip=True) for td in t.find_all("td")]
        if any("Product" in h for h in headers):
            target_table = t
            break
    if target_table is None:
        return None

    rows = []
    for tr in target_table.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if cells:
            rows.append(cells)

    if len(rows) <= 1:
        return None
    
    rows = normalize_html_rows(rows)

    df = pd.DataFrame(rows[1:], columns=rows[0])
    df.columns = [c.strip().replace("\xa0", " ") for c in df.columns]

    # ⚠️ Do NOT add issuer here (run_parser does it)

    # Meta info (optional)
    import re
    text = soup.get_text(" ", strip=True)
    trace_match = re.search(r"TraceId:\s*([A-Za-z0-9]+)", text)
    pricing_ref_match = re.search(r"Pricing Reference IDs:\s*([A-Za-z0-9]+)", text)
    ref_match = re.search(r"Ref\s*:\s*([^\s]+)", text)

    df["trace_id"] = trace_match.group(1) if trace_match else None
    df["pricing_ref_id"] = pricing_ref_match.group(1) if pricing_ref_match else None
    df["ref"] = ref_match.group(1) if ref_match else None

    return df


# =========================
# Leonteq Extractor
# =========================
def extract_leonteq(path: str) -> pd.DataFrame | None:
    try:
        dfs = pd.read_html(path, flavor="lxml")
    except Exception as e:
        return None

    if not dfs:
        return None

    for i, df in enumerate(dfs):
        # promote first row as header
        new_header = df.iloc[0].tolist()
        df = df[1:]
        df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in new_header]

        # drop fully empty columns
        df = df.dropna(axis=1, how="all")


        return df

    return None

# =========================
# Swissquote Extractor
# =========================

def extract_swissquote(html: str) -> pd.DataFrame | None:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None

    target_table = None
    for t in tables:
        headers = [th.get_text(" ", strip=True) for th in t.find_all("th")]
        if "Product Type" in headers and "Currency" in headers:
            target_table = t
            break

    if target_table is None:
        return None

    # --- Extract rows ---
    rows = []
    for tr in target_table.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)

    if len(rows) <= 1:
        return None
    
    rows = normalize_html_rows(rows)

    df = pd.DataFrame(rows[1:], columns=rows[0])
    df.columns = [c.strip().replace("\xa0", " ") for c in df.columns]

    # --- Extract coupon from first cell (each row) ---
    coupons = []
    for val in df.iloc[:, 0]:  # first column
        m = re.search(r"([\d\.,]+)\s*\(coupon p\.a\.\)", val, flags=re.I)
        coupons.append(m.group(1).replace(",", ".") if m else None)

    df["Coupon Rate (%)"] = coupons

    return df


# =========================
# Extractor for Nomura
# =========================
def extract_nomura(html: str) -> pd.DataFrame | None:
    """Parse Nomura pricing emails.

    Heuristic: choose the first HTML table that contains standard headers
    like 'Product' and 'Currency'. Fall back to the first table if none
    matched. Returns a DataFrame with raw headers; normalization is handled
    by Normalizers.py (normalize_nomura).
    """
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        # Plain-text fallback: try to parse tab-separated lines
        text = soup.get_text("\n", strip=True)
        if "\t" in text:
            lines = [ln for ln in text.splitlines() if ln.strip()]
            if len(lines) >= 2:
                headers = [h.strip() for h in lines[0].split("\t")]
                data = [[c.strip() for c in ln.split("\t")] for ln in lines[1:]]
                # Pad/truncate rows to header length
                data = [row + [None] * (len(headers) - len(row)) if len(row) < len(headers) else row[:len(headers)] for row in data]
                try:
                    df = pd.DataFrame(data, columns=headers)
                    return df
                except Exception:
                    pass
        return None

    target_table = None
    for t in tables:
        headers = [th.get_text(" ", strip=True) for th in t.find_all(["th", "td"])]
        header_line = " ".join(headers)
        if any(h in header_line for h in ["Product", "Currency", "Coupon p.a.", "Tenor (m)"]):
            target_table = t
            break
    if target_table is None:
        target_table = tables[0]

    rows = []
    for tr in target_table.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)

    if len(rows) <= 1:
        # Try pandas fallback in case thead/tbody structure confuses manual scrape
        try:
            dfs = pd.read_html(str(target_table))
        except Exception:
            dfs = []
        if dfs:
            df = dfs[0]
            df.columns = [str(c).strip().replace("\xa0", " ") for c in df.columns]
            return df
        return None

    # Normalize multi-line/nbsp and promote first row as headers
    rows = [[c.replace("\xa0", " ").replace("\n", " ").strip() for c in r] for r in rows]
    df = pd.DataFrame(rows[1:], columns=rows[0])
    df.columns = [c.strip().replace("\xa0", " ").replace("\n", " ") for c in df.columns]
    return df



