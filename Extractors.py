
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

    rows = []
    for tr in target_table.find_all("tr"):
        cells = [td.get_text(" ", strip=True).replace("\n", " ") for td in tr.find_all("td")]
        if cells:
            rows.append(cells)

    if len(rows) <= 1:
        return None
    
    rows = normalize_html_rows(rows)

    # first row is header
    df = pd.DataFrame(rows[1:], columns=rows[0])
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
    if not tables:
        return None

    # MS: first table contains the pricing grid
    target_table = tables[0]

    # Use pandas read_html to respect headers
    df_list = pd.read_html(str(target_table))
    if not df_list:
        return None
    df = df_list[0]

    # Normalize column names
    df.columns = [c.strip().replace("\xa0", " ").replace("\n", " ") for c in df.columns]

    return df

# =========================
# Extractor for JPM
# =========================

def extract_jpm(html):
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None

    required_headers = {"product", "tenor (m)", "coupon p.a. (%)"}

    for i, t in enumerate(tables):
        df_list = pd.read_html(str(t))
        if not df_list: 
            continue
        df = df_list[0]
        headers = [str(c).strip().lower() for c in df.columns]

        if required_headers.issubset(set(headers)):
            return df

    return None

# =========================
# Extractor for UBS
# =========================

def extract_ubs(html: str) -> pd.DataFrame | None:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None

    for i, t in enumerate(tables):
        try:
            df_list = pd.read_html(str(t))
        except Exception:
            continue
        if not df_list:
            continue

        df = df_list[0]
        headers = [str(c).strip() for c in df.columns]

        required = {"Product", "Currency", "Tenor (m)", "Coupon p.a. (%)"}
        if required.issubset(set(headers)):
            return df
    return None

# =========================
# Extractor for Marex
# =========================

def extract_marex(html: str) -> pd.DataFrame | None:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None

    for i, t in enumerate(tables):
        try:
            df_list = pd.read_html(str(t))
        except Exception:
            continue
        if not df_list:
            continue

        df = df_list[0]
        headers = [str(c).strip() for c in df.columns]

        required = {"Structure", "Currency", "Tenor (m)", "Coupon p.a. (%)"}
        if required.issubset(set(headers)):
            return df
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
        try:
            df_list = pd.read_html(str(t), header=0)
        except Exception:
            continue
        if not df_list:
            continue

        raw = df_list[0]

        # First column = field names (Product, Currency, etc.)
        # Remaining columns = separate products
        if raw.shape[0] < 5 or raw.shape[1] < 2:
            continue

        # transpose into normal orientation
        df = raw.set_index(raw.columns[0]).T.reset_index(drop=True)

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



