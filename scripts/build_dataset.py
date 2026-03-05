"""
build_dataset.py
Reads raw ABS and RBA Excel files, extracts key economic indicators,
and produces a single tidy CSV file for use in Power BI.

Output schema
-------------
date        : datetime – observation date (end-of-period)
indicator   : str      – series name
value       : float    – observation value
unit        : str      – unit of measure (e.g. "Index", "Percent", "$ Million")
frequency   : str      – "Monthly", "Quarterly", "Annual"
source      : str      – "ABS" or "RBA"
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Callable, Dict, List

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def debug_abs(path: Path) -> None:
    """
    Print diagnostic information for an ABS Excel file:
      - file name and available sheets
      - sheet chosen, detected series_row and data_start
      - first 10 series IDs
      - first 10 series descriptions (from the detected description row in meta_raw)
      - a warning if descriptions appear to be missing or malformed
    """
    print(f"\n{'='*60}")
    print(f"DEBUG ABS: {path.name}")
    print(f"{'='*60}")
    try:
        xls = pd.ExcelFile(path)
        print(f"  Sheets     : {xls.sheet_names[:8]}{' ...' if len(xls.sheet_names) > 8 else ''}")

        df = _read_abs_sheet(path)
        series_ids = list(df.columns)

        print(f"  Sheet used : {df.attrs.get('sheet_used')}")
        print(f"  Series row : {df.attrs.get('series_row')} (0-based)")
        print(f"  Data start : {df.attrs.get('data_start')} (0-based)")
        print(f"  Total series in sheet : {len(series_ids)}")
        print(f"  Series IDs (first 10) : {series_ids[:10]}")

        descriptions = _get_descriptions(df)

        print(f"  Descriptions (first 10):")
        print(f"  Descriptions (first 10):")
        for sid, desc in zip(series_ids[:10], descriptions[:10]):
            print(f"    {sid!s:<16} → {desc}")

        # Warn if descriptions look empty or suspiciously short
        empty_descs = [d for d in descriptions if not d or d.lower() in ("nan", "none")]
        short_descs = [d for d in descriptions if d and 0 < len(d) < 5]
        if empty_descs:
            print(
                f"  WARNING: {len(empty_descs)}/{len(descriptions)} descriptions are empty.",
                file=sys.stderr,
            )
        if short_descs:
            print(
                f"  WARNING: {len(short_descs)} descriptions are suspiciously short: {short_descs[:5]}",
                file=sys.stderr,
            )

    except Exception as exc:
        print(f"  ERROR during debug: {exc}", file=sys.stderr)

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
CLEAN_DIR = ROOT / "data" / "clean"
OUTPUT_FILE = CLEAN_DIR / "economic_indicators.csv"

# ---------------------------------------------------------------------------
# ABS time-series Excel format helpers
#
# ABS Data1-style sheets contain a variable-length header block followed by
# time-series data.  The layout is detected at runtime rather than assumed:
#   series_row : row where column A contains "Series ID" (case-insensitive)
#   data_start : first row after series_row where column A is a parseable date
# ---------------------------------------------------------------------------


def _choose_abs_sheet(xls: pd.ExcelFile) -> str:
    """
    Pick the most likely ABS data sheet from an Excel file.
    Preference order:
      1) 'Data1'
      2) any sheet ending with '_Latest'
      3) any sheet ending with '_Data' or named 'Data'
      4) first sheet
    """
    names = xls.sheet_names
    lowered = {str(n).strip().lower(): n for n in names}

    if "data1" in lowered:
        return lowered["data1"]

    latest = [n for n in names if str(n).strip().lower().endswith("_latest")]
    if latest:
        return latest[0]

    data = [n for n in names if str(n).strip().lower().endswith("_data") or str(n).strip().lower() == "data"]
    if data:
        return data[0]

    return names[0]


def _read_abs_sheet(path: Path, sheet: Optional[str] = None) -> pd.DataFrame:
    """
    Return the data block from an ABS time-series sheet.

    Auto-detects:
      - series_row : first row where column A contains both 'series' and 'id'
      - data_start : first row after series_row where column A is a parseable date

    Returns a DataFrame where:
      - index   = parsed dates
      - columns = ABS series IDs read from series_row, column B onward
      - attrs["sheet_used"]  = name of the sheet read
      - attrs["series_row"]  = detected 0-based row index of the Series ID row
      - attrs["data_start"]  = detected 0-based row index of the first data row
      - attrs["meta_raw"]    = raw header block (rows 0..data_start-1)

    Raises ValueError if series_row or data_start cannot be detected.
    """
    xls = pd.ExcelFile(path)
    if sheet is None:
        sheet = _choose_abs_sheet(xls)

    raw = pd.read_excel(path, sheet_name=sheet, header=None)

    # --- 1. Detect series_row ------------------------------------------------
    series_row: Optional[int] = None
    for i, val in enumerate(raw.iloc[:, 0]):
        text = str(val).lower().strip()
        if "series" in text and "id" in text:
            series_row = i
            break

    if series_row is None:
        raise ValueError(
            f"Could not find a 'Series ID' row in sheet '{sheet}' of {path.name}. "
            "Column A had no cell containing both 'series' and 'id'."
        )

    # --- 2. Detect data_start ------------------------------------------------
    data_start: Optional[int] = None
    for i in range(series_row + 1, len(raw)):
        val = raw.iloc[i, 0]
        if pd.isna(val):
            continue
        try:
            pd.to_datetime(val)
            data_start = i
            break
        except Exception:
            continue

    if data_start is None:
        raise ValueError(
            f"Could not find the data block in sheet '{sheet}' of {path.name}. "
            "No row after the Series ID row had a parseable date in column A."
        )

    # --- 3. Read series IDs from series_row, col B onward --------------------
    series_ids = [str(s).strip() for s in raw.iloc[series_row, 1:].tolist()]

    # --- 4. Build data DataFrame ---------------------------------------------
    data_block = raw.iloc[data_start:, :].copy()
    dates = pd.to_datetime(data_block.iloc[:, 0], errors="coerce")
    values = data_block.iloc[:, 1 : 1 + len(series_ids)].copy()
    values.columns = series_ids
    values.index = dates
    values = values[values.index.notna()]
    values = values.apply(pd.to_numeric, errors="coerce")

    # --- 5. Attach attrs -----------------------------------------------------
    values.attrs["sheet_used"] = sheet
    values.attrs["series_row"] = series_row
    values.attrs["data_start"] = data_start
    values.attrs["meta_raw"] = raw.iloc[:data_start, :]

    return values


def _get_descriptions(df: pd.DataFrame) -> List[str]:
    """
    Return per-series description strings aligned to df.columns,
    using the meta_raw header block attached by _read_abs_sheet().
    The description row is whichever row has the most non-empty string cells.
    """
    meta_raw: Optional[pd.DataFrame] = df.attrs.get("meta_raw")
    if meta_raw is None:
        raise ValueError("df.attrs['meta_raw'] is not set; ensure _read_abs_sheet() populated it.")

    meta_data = meta_raw.iloc[:, 1:]  # skip col A (row-label column)

    def _nonempty_string_count(row: pd.Series) -> int:
        return sum(1 for v in row if pd.notna(v) and str(v).strip() not in ("", "nan"))

    row_counts = [_nonempty_string_count(meta_data.iloc[i]) for i in range(len(meta_data))]
    desc_row_idx = row_counts.index(max(row_counts))
    raw_descs = [str(v).strip() for v in meta_data.iloc[desc_row_idx].tolist()]
    return raw_descs[: len(df.columns)]


def extract_abs_by_description(
    df: pd.DataFrame,
    any_groups: List[List[str]],
    indicator_name: str,
    unit: str,
    frequency: str,
    prefer_keywords: Optional[List[str]] = None,
    print_descs_on_miss: bool = False,
) -> pd.DataFrame:
    """
    Find the best-matching series by searching descriptions with any-of-groups logic.

    any_groups: list of keyword groups.  A series matches when, for EVERY group,
    at least ONE keyword in that group appears in the description (case-insensitive).

    prefer_keywords: optional list of words used to rank multiple matches;
    a candidate scores +1 for each prefer_keyword found in its description.

    print_descs_on_miss: if True and no match is found, print the first 60
    descriptions to stderr so the caller can diagnose the mismatch.

    Returns a tidy long DataFrame or an empty DataFrame on no match.
    """
    descriptions = _get_descriptions(df)

    def _matches(desc: str) -> bool:
        d = desc.lower()
        return all(
            any(kw.lower() in d for kw in group)
            for group in any_groups
        )

    candidates = [(col, desc) for col, desc in zip(df.columns, descriptions) if _matches(desc)]

    if not candidates:
        sheet_used = df.attrs.get("sheet_used", "unknown")
        print(
            f"  WARNING: No series matching any_groups={any_groups} "
            f"in sheet '{sheet_used}' of {df.attrs.get('meta_raw', pd.DataFrame()).shape} – skipping.",
            file=sys.stderr,
        )
        if print_descs_on_miss:
            print(f"  First 60 descriptions found in '{sheet_used}':", file=sys.stderr)
            for i, desc in enumerate(descriptions[:60]):
                print(f"    [{i:>3}] {desc}", file=sys.stderr)
        return pd.DataFrame()

    # Rank by preference keywords (higher score = better match)
    if prefer_keywords:
        def _score(desc: str) -> int:
            d = desc.lower()
            return sum(1 for kw in prefer_keywords if kw.lower() in d)
        candidates.sort(key=lambda x: _score(x[1]), reverse=True)

    chosen_col, chosen_desc = candidates[0]

    series = df[chosen_col].dropna().reset_index()
    series.columns = ["date", "value"]
    series["indicator"] = indicator_name
    series["unit"] = unit
    series["frequency"] = frequency
    series["source"] = "ABS"
    return series[["date", "indicator", "value", "unit", "frequency", "source"]]


# ---------------------------------------------------------------------------
# Per-dataset extractors
# ---------------------------------------------------------------------------

def extract_cpi(path: Path) -> pd.DataFrame:
    """CPI All Groups, Weighted Average of Eight Capital Cities (quarterly)."""
    print("  Processing CPI ...")
    try:
        df = _read_abs_sheet(path)
        return extract_abs_by_description(
            df,
            any_groups=[
                ["consumer price index", "cpi"],
                ["all groups", "weighted average", "eight capital cities", "capital cities"],
            ],
            indicator_name="CPI",
            unit="Index",
            frequency="Quarterly",
            prefer_keywords=["all groups", "weighted average"],
            print_descs_on_miss=True,
        )
    except Exception as exc:
        print(f"  ERROR extracting CPI: {exc}", file=sys.stderr)
        return pd.DataFrame()


def extract_unemployment(path: Path) -> pd.DataFrame:
    """Unemployment rate, seasonally adjusted (monthly)."""
    print("  Processing Unemployment ...")
    try:
        df = _read_abs_sheet(path)
        return extract_abs_by_description(
            df,
            any_groups=[["unemployment rate"]],
            indicator_name="Unemployment Rate",
            unit="Percent",
            frequency="Monthly",
            prefer_keywords=["australia", "total"],
        )
    except Exception as exc:
        print(f"  ERROR extracting Unemployment: {exc}", file=sys.stderr)
        return pd.DataFrame()


def extract_wpi(path: Path) -> pd.DataFrame:
    """Wage Price Index, total hourly rates excl. bonuses, all sectors (quarterly)."""
    print("  Processing Wage Price Index ...")
    try:
        df = _read_abs_sheet(path)
        return extract_abs_by_description(
            df,
            any_groups=[
                ["wage price index", "wpi", "wages", "hourly rates"],
                ["total", "australia", "all sectors", "excluding bonuses", "excl bonuses", "bonus"],
            ],
            indicator_name="Wage Price Index",
            unit="Index",
            frequency="Quarterly",
            prefer_keywords=["total", "australia"],
            print_descs_on_miss=True,
        )
    except Exception as exc:
        print(f"  ERROR extracting WPI: {exc}", file=sys.stderr)
        return pd.DataFrame()


def extract_gdp(path: Path) -> pd.DataFrame:
    """GDP chain volume measure, seasonally adjusted (quarterly)."""
    print("  Processing GDP ...")
    try:
        df = _read_abs_sheet(path)
        result = extract_abs_by_description(
            df,
            any_groups=[["gross domestic product"]],
            indicator_name="GDP",
            unit="$ Million",
            frequency="Quarterly",
            prefer_keywords=["australia", "total", "chain volume"],
        )
        if result.empty:
            result = extract_abs_by_description(
                df,
                any_groups=[["gdp"]],
                indicator_name="GDP",
                unit="$ Million",
                frequency="Quarterly",
                prefer_keywords=["australia", "total"],
            )
        return result
    except Exception as exc:
        print(f"  ERROR extracting GDP: {exc}", file=sys.stderr)
        return pd.DataFrame()


def extract_cash_rate(path: Path) -> pd.DataFrame:
    """RBA cash rate target (monthly)."""
    print("  Processing RBA Cash Rate ...")
    try:
        raw = pd.read_excel(path, sheet_name=0, header=None)

        # Locate the header row: a row where col A contains "Title"
        header_row = None
        for i, val in enumerate(raw.iloc[:, 0]):
            if pd.notna(val) and str(val).strip().lower() == "title":
                header_row = i
                break

        if header_row is None:
            # Fallback: find first row where col A parses as a date, then header is one row above
            for i, val in enumerate(raw.iloc[:, 0]):
                try:
                    pd.to_datetime(val)
                    header_row = max(i - 1, 0)
                    break
                except Exception:
                    continue

        df = pd.read_excel(path, sheet_name=0, header=header_row)

        # Find the cash rate column by searching column titles
        cash_col = None
        for col in df.columns:
            col_l = str(col).lower()
            if "cash rate" in col_l and ("target" in col_l or "rate" in col_l):
                cash_col = col
                break

        if cash_col is None:
            for col in df.columns:
                if "cash" in str(col).lower():
                    cash_col = col
                    break

        if cash_col is None:
            cash_col = df.columns[1]
            print(f"  WARNING: Could not identify cash rate column; using '{cash_col}'.", file=sys.stderr)

        date_col = df.columns[0]
        series = df[[date_col, cash_col]].copy()
        series.columns = ["date", "value"]
        series["date"] = pd.to_datetime(series["date"], errors="coerce")
        series["value"] = pd.to_numeric(series["value"], errors="coerce")
        series = series.dropna(subset=["date", "value"])

        series["indicator"] = "Cash Rate Target"
        series["unit"] = "Percent"
        series["frequency"] = "Monthly"
        series["source"] = "RBA"
        return series[["date", "indicator", "value", "unit", "frequency", "source"]]

    except Exception as exc:
        print(f"  ERROR extracting Cash Rate: {exc}", file=sys.stderr)
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Build pipeline
# ---------------------------------------------------------------------------

EXTRACTORS: Dict[str, Callable[[Path], pd.DataFrame]] = {
    "cpi.xlsx": extract_cpi,
    "unemployment.xlsx": extract_unemployment,
    "wpi.xlsx": extract_wpi,
    "gdp.xlsx": extract_gdp,
    "rba_cash_rate.xlsx": extract_cash_rate,
}


def clean_combined(df: pd.DataFrame) -> pd.DataFrame:
    """Apply final formatting and quality checks to the combined dataset."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["date", "value"])

    # Normalise dates to period-end by frequency for correct Power BI time intelligence:
    #   Monthly   -> end of that calendar month
    #   Quarterly -> end of that fiscal/calendar quarter
    #   All others -> end of month (safe fallback)
    monthly_mask = df["frequency"].str.lower() == "monthly"
    quarterly_mask = df["frequency"].str.lower() == "quarterly"
    other_mask = ~(monthly_mask | quarterly_mask)

    df.loc[monthly_mask, "date"] = df.loc[monthly_mask, "date"] + pd.offsets.MonthEnd(0)
    df.loc[quarterly_mask, "date"] = df.loc[quarterly_mask, "date"] + pd.offsets.QuarterEnd(0)
    df.loc[other_mask, "date"] = df.loc[other_mask, "date"] + pd.offsets.MonthEnd(0)

    df = df.sort_values(["indicator", "date"]).reset_index(drop=True)
    return df


def save_output(df: pd.DataFrame) -> None:
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False, date_format="%Y-%m-%d")
    print(f"\n  Saved {len(df):,} rows → {OUTPUT_FILE}")


def main() -> None:
    frames: List[pd.DataFrame] = []
    missing: List[str] = []

    for filename, extractor in EXTRACTORS.items():
        path = RAW_DIR / filename
        if not path.exists():
            print(f"  SKIP: {filename} not found in {RAW_DIR}")
            missing.append(filename)
            continue

        if filename != "rba_cash_rate.xlsx" and os.getenv("DEBUG_ABS") == "1":
            debug_abs(path)

        result = extractor(path)
        if not result.empty:
            frames.append(result)

    if not frames:
        print("ERROR: No data extracted. Run fetch_abs.py and fetch_rba.py first.", file=sys.stderr)
        sys.exit(1)

    combined = pd.concat(frames, ignore_index=True)
    combined = clean_combined(combined)
    save_output(combined)

    print(
        f"\nSummary:\n"
        f"  Indicators : {combined['indicator'].nunique()}\n"
        f"  Date range : {combined['date'].min().date()} – {combined['date'].max().date()}\n"
        f"  Total rows : {len(combined):,}"
    )
    if missing:
        print(f"\n  Files not found (skipped): {', '.join(missing)}", file=sys.stderr)


if __name__ == "__main__":
    main()