"""Download the Cookie Cats dataset used by the showcase analysis.

The file is small (~1.5 MB) and public, so it is fetched on demand rather than
committed. Run once:

    python analysis/fetch_data.py
"""

from __future__ import annotations

import os
import urllib.request

URL = (
    "https://raw.githubusercontent.com/thegarrickchu/"
    "Mobile-Games-Ab-testing-with-Cookie-Cats/master/datasets/cookie_cats.csv"
)
DEST = os.path.join("data", "raw", "cookie_cats.csv")

EXPECTED_COLUMNS = {"userid", "version", "sum_gamerounds", "retention_1", "retention_7"}
EXPECTED_ROWS = 90_189


def fetch(dest: str = DEST, force: bool = False) -> str:
    """Download the dataset unless it is already on disk."""
    if os.path.exists(dest) and not force:
        print(f"Already present: {dest}")
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print(f"Downloading {URL}")
    urllib.request.urlretrieve(URL, dest)

    import pandas as pd

    df = pd.read_csv(dest)
    missing = EXPECTED_COLUMNS - set(df.columns)
    if missing:
        raise RuntimeError(f"Downloaded file is missing columns: {missing}")
    if len(df) != EXPECTED_ROWS:
        print(f"Warning: expected {EXPECTED_ROWS:,} rows, got {len(df):,}")
    print(f"Saved {len(df):,} rows to {dest}")
    return dest


if __name__ == "__main__":
    fetch()
