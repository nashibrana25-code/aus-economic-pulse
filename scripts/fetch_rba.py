"""
fetch_rba.py
Downloads Reserve Bank of Australia (RBA) macroeconomic data
and saves it into data/raw/.
"""

import sys
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

# RBA Statistical Tables – "xls" links resolve to the current published file.
DATASETS = {
    "rba_cash_rate": (
        "https://www.rba.gov.au/statistics/tables/xls/a02hist.xlsx"
    ),
}

TIMEOUT = 60  # seconds
HEADERS = {"User-Agent": "aus-economic-pulse/1.0 (data pipeline)"}


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def ensure_raw_dir() -> None:
    """Create data/raw if it does not already exist."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)


def download_file(name: str, url: str) -> bool:
    """
    Download a file from *url* and save it to data/raw/<name>.xlsx.

    Returns True on success, False on failure.
    """
    dest = RAW_DIR / f"{name}.xlsx"
    print(f"  Downloading {name} ...")

    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT, stream=True)
        response.raise_for_status()

        with dest.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=8192):
                fh.write(chunk)

        size_kb = dest.stat().st_size / 1024
        print(f"  Saved {dest.name} ({size_kb:.1f} KB)")
        return True

    except requests.exceptions.HTTPError as exc:
        print(f"  ERROR [{name}] HTTP {exc.response.status_code}: {url}", file=sys.stderr)
    except requests.exceptions.ConnectionError:
        print(f"  ERROR [{name}] Connection failed: {url}", file=sys.stderr)
    except requests.exceptions.Timeout:
        print(f"  ERROR [{name}] Request timed out after {TIMEOUT}s: {url}", file=sys.stderr)
    except requests.exceptions.RequestException as exc:
        print(f"  ERROR [{name}] {exc}", file=sys.stderr)

    return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Target directory: {RAW_DIR}")
    ensure_raw_dir()

    results = {}
    for name, url in DATASETS.items():
        results[name] = download_file(name, url)

    succeeded = [n for n, ok in results.items() if ok]
    failed = [n for n, ok in results.items() if not ok]

    print(f"\nDone. {len(succeeded)}/{len(DATASETS)} datasets downloaded successfully.")
    if failed:
        print(f"Failed: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
