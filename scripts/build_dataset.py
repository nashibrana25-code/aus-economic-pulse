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

import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
CLEAN_DIR = ROOT / "data" / "clean"
OUTPUT_FILE = CLEAN_DIR / "economic_indicators.csv"

# ---------------------------------------------------------------------------
# ABS time-series Excel format helpers
#
# ABS "Data1"-style sheets follow a fixed header layout:
#   Row 1        : Series description
#   Row 2        : Series type
#   Row 3        : Data type
#   Row 4        : Frequency
#   Row 5        : Collection month
#   Row 6        : Series ID
#   Row 7        : Number of observations
#   Row 8        : Unit
#   Row 9        : (blank)
#   Row 10+      : data  (col A = date, remaining cols = series values)
# ---------------------------------------------------------------------------

ABS_HEADER_ROWS = 9  # data begins on row 10 (0-indexed: row 9)


def _read_abs_sheet(path: Path, sheet: str = "Data1") -> pd.DataFrame:
    """
    Return the raw header block and data block from an ABS time-series sheet.

    Returns a DataFrame where:
      - index   = parsed dates
      - columns = ABS series IDs (row 6 of the header)
      - attrs["meta"] = DataFrame with the 9-row header keyed by series ID
    """
    raw = pd.read_excel(path, sheet_name=sheet, header=None)

    meta = raw.iloc[:ABS_HEADER_ROWS, 1:]          # header rows, skip col A
    data = raw.iloc[ABS_HEADER_ROWS:, :].copy()    # data rows

    data.columns = raw.iloc[0, :]                  # use row 1 as column names placeholder
    # Proper column names come from ABS header row index 5 (Series ID)
    series_ids = raw.iloc[5, 1:].tolist()
    dates = pd.to_datetime(data.iloc[:, 0], errors="coerce")
    values = data.iloc[:, 1:].copy()
    values.columns = series_ids
    values.index = dates
    values = values[values.index.notna()]
    values = values.apply(pd.to_numeric, errors="coerce")

    # Attach metadata as a dict keyed by series ID
    meta.index = [
        "description", "series_type", "data_type",
        "frequency", "collection_month", "series_id",
        "num_obs", "unit",
        "blank",
    ]
    meta.columns = series_ids
    values.attrs["meta"] = meta

    return values


def _abs_to_long(
    df: pd.DataFrame,
    series_id: str,
    indicator_name: str,
    unit: str,
    frequency: str,
) -> pd.DataFrame:
    """
    Extract a single series from an ABS DataFrame and return a tidy long table.
    Falls back gracefully if *series_id* is not present.
    """
    if series_id not in df.columns:
        # Try partial match (series IDs sometimes have trailing spaces)
        matches = [c for c in df.columns if series_id.strip() in str(c).strip()]
        if not matches:
            print(f"  WARNING: series '{series_id}' not found – skipping.", file=sys.stderr)
            return pd.DataFrame()
        series_id = matches[0]

    series = df[series_id].dropna().reset_index()
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
        # ABS series ID for CPI All Groups weighted average
        return _abs_to_long(
            df,
            series_id="A2325846C",
            indicator_name="CPI All Groups",
            unit="Index (2011-12=100)",
            frequency="Quarterly",
        )
    except Exception as exc:
        print(f"  ERROR extracting CPI: {exc}", file=sys.stderr)
        return pd.DataFrame()


def extract_unemployment(path: Path) -> pd.DataFrame:
    """Unemployment rate, seasonally adjusted (monthly)."""
    print("  Processing Unemployment ...")
    try:
        df = _read_abs_sheet(path)
        # ABS series ID for total unemployment rate, seasonally adjusted
        return _abs_to_long(
            df,
            series_id="A84423050A",
            indicator_name="Unemployment Rate",
            unit="Percent",
            frequency="Monthly",
        )
    except Exception as exc:
        print(f"  ERROR extracting Unemployment: {exc}", file=sys.stderr)
        return pd.DataFrame()


def extract_wpi(path: Path) -> pd.DataFrame:
    """Wage Price Index, total hourly rates excl. bonuses, all sectors (quarterly)."""
    print("  Processing Wage Price Index ...")
    try:
        df = _read_abs_sheet(path)
        # ABS series ID for WPI total, private and public, Australia
        return _abs_to_long(
            df,
            series_id="A2603606J",
            indicator_name="Wage Price Index",
            unit="Index (2017-18=100)",
            frequency="Quarterly",
        )
    except Exception as exc:
        print(f"  ERROR extracting WPI: {exc}", file=sys.stderr)
        return pd.DataFrame()


def extract_gdp(path: Path) -> pd.DataFrame:
    """GDP chain volume measure, seasonally adjusted (quarterly)."""
    print("  Processing GDP ...")
    try:
        df = _read_abs_sheet(path)
        # ABS series ID for GDP chain volume measures
        return _abs_to_long(
            df,
            series_id="A2304402X",
            indicator_name="GDP",
            unit="$ Million",
            frequency="Quarterly",
        )
    except Exception as exc:
        print(f"  ERROR extracting GDP: {exc}", file=sys.stderr)
        return pd.DataFrame()


def extract_cash_rate(path: Path) -> pd.DataFrame:
    """RBA cash rate target (monthly)."""
    print("  Processing RBA Cash Rate ...")
    try:
        # RBA a02hist.xlsx: skip description rows; column A = date, find cash rate column
        raw = pd.read_excel(path, sheet_name=0, header=None)

        # Locate the header row: first row where col A contains "Title" or a year-like date
        header_row = None
        for i, val in enumerate(raw.iloc[:, 0]):
            if pd.notna(val) and str(val).strip().lower() == "title":
                header_row = i
                break

        if header_row is None:
            # Fallback: find first row where col A parses as a date
            for i, val in enumerate(raw.iloc[:, 0]):
                try:
                    pd.to_datetime(val)
                    header_row = i - 1
                    break
                except Exception:
                    continue

        data_start = header_row + 1 if header_row is not None else 1
        df = pd.read_excel(path, sheet_name=0, header=header_row)

        # Find the cash rate column by searching column titles
        cash_col = None
        for col in df.columns:
            if "cash rate" in str(col).lower() or "cash" in str(col).lower():
                cash_col = col
                break

        if cash_col is None:
            # Use the second column as fallback
            cash_col = df.columns[1]
            print(
                f"  WARNING: Could not identify cash rate column; using '{cash_col}'.",
                file=sys.stderr,
            )

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

EXTRACTORS = {
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
    df = df.sort_values(["indicator", "date"]).reset_index(drop=True)
    # Normalise date to end-of-month for consistent time intelligence in Power BI
    df["date"] = df["date"] + pd.offsets.MonthEnd(0)
    return df


def save_output(df: pd.DataFrame) -> None:
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False, date_format="%Y-%m-%d")
    print(f"\n  Saved {len(df):,} rows → {OUTPUT_FILE}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    frames = []
    missing = []

    for filename, extractor in EXTRACTORS.items():
        path = RAW_DIR / filename
        if not path.exists():
            print(f"  SKIP: {filename} not found in {RAW_DIR}")
            missing.append(filename)
            continue
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
