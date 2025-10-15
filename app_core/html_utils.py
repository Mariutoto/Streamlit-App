from __future__ import annotations

from bs4 import BeautifulSoup
import pandas as pd
from typing import List


def normalize_html_rows(rows: List[List[str]]) -> List[List[str]]:
    """
    Ensure every row has the same number of columns as the header row.
    Pads with empty strings or trims extras as needed.
    """
    if not rows:
        return rows

    max_len = len(rows[0])
    normalized = []
    for r in rows:
        row = list(r)
        if len(row) < max_len:
            row.extend([""] * (max_len - len(row)))
        elif len(row) > max_len:
            row = row[:max_len]
        normalized.append(row)
    return normalized


def soup_tables_to_rows(soup: BeautifulSoup) -> list[list[list[str]]]:
    """Return list of tables, each table is list of rows, each row is list of cell texts."""
    tables = []
    for t in soup.find_all("table"):
        rows = []
        for tr in t.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


def extract_best_table(html: str) -> pd.DataFrame | None:
    """
    Heuristic: pick the table with the largest number of data rows (> 1).
    Normalize row lengths before building DataFrame.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    all_tables = soup_tables_to_rows(soup)
    if not all_tables:
        return None

    # choose the table with most rows where at least 2 rows present
    candidate = None
    for rows in all_tables:
        if len(rows) > 1 and (candidate is None or len(rows) > len(candidate)):
            candidate = rows
    if not candidate or len(candidate) <= 1:
        return None

    cand = normalize_html_rows(candidate)
    df = pd.DataFrame(cand[1:], columns=cand[0])
    df.columns = [str(c).strip().replace("\xa0", " ") for c in df.columns]
    return df

