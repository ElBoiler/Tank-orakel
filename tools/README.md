# Tank-Orakel — curve builder

`build_curve.py` computes `curve.json` (the historical price curve the app uses)
from the **Tankerkönig historical dataset**. It is designed to run as a regular
local job (e.g. Windows Task Scheduler) that rebuilds and pushes `curve.json`;
Cloudflare Pages then auto-redeploys and serves the fresh file. Nothing about the
running app or the Cloudflare Functions needs to change — the app already fetches
`curve.json`.

## What it produces

`curve.json` in the repo root, in the exact schema `index.html` consumes:
`regimes[fuel][regime]` (`post_kpang` / `pre_kpang`) with `overall`
(`minute`/`p25`/`p50`/`p75`), `post_noon_decay` (per hour: `median_ct_vs_noon`,
`share_cheaper_than_noon`), `weekday_median_dev_ct`, `by_plz1`, plus
`n_station_days`, `cheapest_minute`, `spread_ct`. Regimes are split by date at
2026-04-01 (the day the 12-Uhr-Regel took effect).

## One-time setup (Windows)

1. Install Python 3.10+ and the dependencies:
   ```
   pip install -r tools\requirements.txt
   ```
2. Clone the Tankerkönig historical data **once** (~20 GB) into `data\`:
   ```
   git clone https://tankerkoenig@dev.azure.com/tankerkoenig/tankerkoenig-data/_git/tankerkoenig-data data\tankerkoenig-data
   ```
   The dataset is licensed **CC BY-NC-SA 4.0** (non-commercial use only).
3. Make sure this repo can `git push origin main` non-interactively (a stored
   credential / PAT). `data\` is gitignored so the 20 GB clone is never committed.

## Run manually

```
python tools\build_curve.py --data data\tankerkoenig-data --out curve.json --window 90
```

- `--window N` rolling window in days (default 90).
- `--end YYYY-MM-DD` last day to include (default: yesterday).

## Schedule it

`update_curve.bat` does the whole cycle: pull data → build → commit → push.
Register it to run nightly (after Tankerkönig publishes the previous day, ~early
morning):

```
schtasks /Create /SC DAILY /ST 05:00 /TN "Tank-Orakel-Curve" ^
  /TR "C:\path\to\Tank-orakel\tools\update_curve.bat"
```

## Notes

- The committed `curve.json` (and the inline fallback in `index.html`) is
  placeholder/demo data until the first real run overwrites it.
- Percentiles are computed from bounded histograms, so memory stays small even
  over long windows; the heavy part is reading the daily CSVs, which is why this
  runs on your machine rather than in a Cloudflare Worker (whose free-tier CPU is
  far too small, and whose paid tier would cost money for the same result).
