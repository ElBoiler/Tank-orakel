#!/usr/bin/env python3
"""Build curve.json for Tank-Orakel from the Tankerkoenig historical dataset.

This is the real replacement for the placeholder curve. It is meant to run as a
regular local job (e.g. Windows Task Scheduler via tools/update_curve.bat), which
then commits and pushes the refreshed curve.json so Cloudflare Pages redeploys.

Data source: the Tankerkoenig historical price data (Azure DevOps repo), licensed
CC BY-NC-SA 4.0 (non-commercial). Clone it once and `git pull` for daily updates:

    git clone https://tankerkoenig@dev.azure.com/tankerkoenig/tankerkoenig-data/_git/tankerkoenig-data

Layout used here:
    <data>/prices/YYYY/MM/YYYY-MM-DD-prices.csv
    <data>/stations/YYYY/MM/YYYY-MM-DD-stations.csv

prices columns:  date, station_uuid, diesel, e5, e10, dieselchange, e5change, e10change
                 (each row is a price-change event; price columns hold new prices in EUR)
stations columns include: uuid, post_code  (plus name/brand/lat/lng/...)

Output schema matches exactly what index.html consumes (see the inline
`curve-fallback` block): regimes[fuel][regime] with overall{minute,p25,p50,p75},
post_noon_decay{hour:{median_ct_vs_noon,share_cheaper_than_noon}},
weekday_median_dev_ct{0..6}, by_plz1{"0".."9":{...}}, plus n_station_days,
cheapest_minute, spread_ct.

Usage:
    python build_curve.py --data ../data/tankerkoenig-data --out ../curve.json --window 90
"""
from __future__ import annotations
import argparse
import datetime as dt
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

# ---- Constants -------------------------------------------------------------
FUELS = ("diesel", "e5", "e10")
GRID_STEP = 15                                  # minutes
GRID = list(range(0, 1440, GRID_STEP))          # 96 sample points per day
NOON_IDX = GRID.index(720)
KPANG_DATE = dt.date(2026, 4, 1)                # 12-Uhr-Regel in force
MIN_STATION_DAYS = 200                          # buckets below this are still
                                                # emitted but the app falls back

# Price histogram domain in ct/l (0.1 ct bins). Covers plausible German prices.
PRICE_LO, PRICE_HI, PRICE_BIN = 100.0, 260.0, 0.1
PRICE_BINS = int(round((PRICE_HI - PRICE_LO) / PRICE_BIN))       # 1600
PRICE_EDGES = np.linspace(PRICE_LO, PRICE_HI, PRICE_BINS + 1)
PRICE_CENTERS = (PRICE_EDGES[:-1] + PRICE_EDGES[1:]) / 2

# Delta-vs-noon histogram domain in ct/l (0.1 ct bins).
DELTA_LO, DELTA_HI, DELTA_BIN = -30.0, 15.0, 0.1
DELTA_BINS = int(round((DELTA_HI - DELTA_LO) / DELTA_BIN))       # 450
DELTA_EDGES = np.linspace(DELTA_LO, DELTA_HI, DELTA_BINS + 1)
DELTA_CENTERS = (DELTA_EDGES[:-1] + DELTA_EDGES[1:]) / 2

REGIONS = ["overall"] + [str(d) for d in range(10)]  # overall + plz1 0..9


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---- Accumulator -----------------------------------------------------------
class Regime:
    """Rolling histograms for one (fuel, regime) combination."""

    def __init__(self):
        # price histograms: region -> [minute][price_bin]
        self.price_hist = {r: np.zeros((len(GRID), PRICE_BINS), np.int64) for r in REGIONS}
        # post-noon delta histograms: region -> hour(12..23) -> [delta_bin]
        self.delta_hist = {r: {h: np.zeros(DELTA_BINS, np.int64) for h in range(12, 24)} for r in REGIONS}
        # cheaper-than-noon counters: region -> hour -> [cheaper, total]
        self.cheaper = {r: {h: np.zeros(2, np.int64) for h in range(12, 24)} for r in REGIONS}
        # weekday daily-median samples: region -> weekday(0..6) -> list of medians
        self.weekday = {r: {w: [] for w in range(7)} for r in REGIONS}
        self.n_station_days = {r: 0 for r in REGIONS}

    def add_station_day(self, region, series_ct, weekday):
        """series_ct: np.array of 96 prices in ct (NaN where unknown)."""
        valid = ~np.isnan(series_ct)
        if valid.sum() < len(GRID) * 0.5:
            return  # too sparse to be a usable station-day
        for r in ("overall", region):
            self.n_station_days[r] += 1
            # price histograms per minute
            idx = np.where(valid)[0]
            bins = np.clip(((series_ct[idx] - PRICE_LO) / PRICE_BIN).astype(int), 0, PRICE_BINS - 1)
            for m_i, b in zip(idx, bins):
                self.price_hist[r][m_i, b] += 1
            # weekday daily median
            self.weekday[r][weekday].append(float(np.nanmedian(series_ct)))
            # post-noon deltas vs the 12:00 price
            noon = series_ct[NOON_IDX]
            if not np.isnan(noon):
                for h in range(12, 24):
                    gi = h * 60 // GRID_STEP
                    if gi >= len(GRID):
                        continue
                    v = series_ct[gi]
                    if np.isnan(v):
                        continue
                    d = v - noon
                    db = int(np.clip((d - DELTA_LO) / DELTA_BIN, 0, DELTA_BINS - 1))
                    self.delta_hist[r][h][db] += 1
                    self.cheaper[r][h][1] += 1
                    if v < noon:
                        self.cheaper[r][h][0] += 1


def hist_percentile(hist_row, centers, q):
    total = hist_row.sum()
    if total == 0:
        return None
    target = q * total
    cum = np.cumsum(hist_row)
    i = int(np.searchsorted(cum, target, side="left"))
    i = min(i, len(centers) - 1)
    return float(centers[i])


def emit_curve_shape(price_hist):
    p25, p50, p75 = [], [], []
    for m_i in range(len(GRID)):
        row = price_hist[m_i]
        p25.append(round(hist_percentile(row, PRICE_CENTERS, 0.25) or 0.0, 1))
        p50.append(round(hist_percentile(row, PRICE_CENTERS, 0.50) or 0.0, 1))
        p75.append(round(hist_percentile(row, PRICE_CENTERS, 0.75) or 0.0, 1))
    return {"minute": GRID, "p25": p25, "p50": p50, "p75": p75}


def emit_decay(reg: "Regime", region):
    out = {}
    for h in range(12, 24):
        med = hist_percentile(reg.delta_hist[region][h], DELTA_CENTERS, 0.50)
        cheaper, total = reg.cheaper[region][h]
        if med is None or total == 0:
            continue
        out[str(h)] = {
            "median_ct_vs_noon": round(med, 1),
            "share_cheaper_than_noon": round(float(cheaper) / float(total), 2),
        }
    return out


def emit_weekday_dev(reg: "Regime", region):
    # deviation of each weekday's median daily-median from the overall median
    all_meds = [m for w in range(7) for m in reg.weekday[region][w]]
    base = float(np.median(all_meds)) if all_meds else 0.0
    out = {}
    for w in range(7):
        vals = reg.weekday[region][w]
        out[str(w)] = round(float(np.median(vals)) - base, 2) if vals else 0.0
    return out


def build_regime_json(reg: "Regime", region_scope="overall"):
    shape = emit_curve_shape(reg.price_hist[region_scope])
    p50 = shape["p50"]
    cheapest_minute = GRID[int(np.argmin(p50))] if p50 else 0
    morning = [p50[i] for i in range(len(GRID)) if GRID[i] < 720 and p50[i] > 0]
    spread = round((p50[NOON_IDX] - min(morning)), 1) if morning and p50[NOON_IDX] else 0.0
    return {
        "n_station_days": int(reg.n_station_days[region_scope]),
        "cheapest_minute": int(cheapest_minute),
        "spread_ct": spread,
        "overall": shape,
        "post_noon_decay": emit_decay(reg, region_scope),
        "weekday_median_dev_ct": emit_weekday_dev(reg, region_scope),
    }


# ---- Data loading ----------------------------------------------------------
def load_station_plz1(data_dir):
    files = sorted(glob.glob(os.path.join(data_dir, "stations", "*", "*", "*-stations.csv")))
    if not files:
        raise SystemExit(f"No stations CSV found under {data_dir}/stations")
    df = pd.read_csv(files[-1], usecols=["uuid", "post_code"], dtype=str)
    df = df.dropna(subset=["uuid", "post_code"])
    df["plz1"] = df["post_code"].str.strip().str[0]
    df = df[df["plz1"].str.match(r"\d", na=False)]
    return dict(zip(df["uuid"], df["plz1"]))


def day_file(data_dir, day):
    return os.path.join(data_dir, "prices", f"{day:%Y}", f"{day:%m}", f"{day:%Y-%m-%d}-prices.csv")


def reconstruct_day(path, fuel, last_price):
    """Return {station_uuid: np.array(96) of ct prices} for one fuel and day.

    `last_price` (dict uuid->ct) provides each station's opening price and is
    updated in place with the day's final price so the next day carries over.
    """
    cols = ["date", "station_uuid", fuel]
    df = pd.read_csv(path, usecols=cols, parse_dates=["date"])
    df = df.dropna(subset=["date", "station_uuid"])
    df = df[df[fuel] > 0]
    if df.empty:
        return {}
    # minutes since local midnight (dataset timestamps are Europe/Berlin wall time)
    df["min"] = df["date"].dt.hour * 60 + df["date"].dt.minute
    df = df.sort_values(["station_uuid", "min"])
    grid = np.array(GRID)
    out = {}
    for uuid, g in df.groupby("station_uuid", sort=False):
        ev_min = g["min"].to_numpy()
        ev_px = g[fuel].to_numpy() * 100.0  # EUR -> ct
        opening = last_price.get(uuid, np.nan)
        # For each grid point take the last event at or before it, else opening.
        pos = np.searchsorted(ev_min, grid, side="right") - 1
        series = np.where(pos >= 0, ev_px[np.clip(pos, 0, len(ev_px) - 1)], opening)
        out[uuid] = series.astype(float)
        last_price[uuid] = ev_px[-1]  # carry over final price (ct)
    return out


# ---- Main ------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Build curve.json from Tankerkoenig history.")
    ap.add_argument("--data", required=True, help="path to cloned tankerkoenig-data repo")
    ap.add_argument("--out", default="curve.json", help="output curve.json path")
    ap.add_argument("--window", type=int, default=90, help="rolling window in days")
    ap.add_argument("--end", default=None, help="last day YYYY-MM-DD (default: yesterday)")
    args = ap.parse_args()

    end = dt.date.fromisoformat(args.end) if args.end else dt.date.today() - dt.timedelta(days=1)
    days = [end - dt.timedelta(days=i) for i in range(args.window - 1, -1, -1)]

    log(f"Loading station -> PLZ1 map from {args.data} ...")
    plz1 = load_station_plz1(args.data)
    log(f"  {len(plz1)} stations mapped.")

    # (fuel, regime) accumulators
    acc = {f: {"post_kpang": Regime(), "pre_kpang": Regime()} for f in FUELS}
    # carry-over opening prices per fuel
    last_price = {f: {} for f in FUELS}

    processed = 0
    for day in days:
        path = day_file(args.data, day)
        if not os.path.exists(path):
            log(f"  skip {day} (no file)")
            continue
        regime = "post_kpang" if day >= KPANG_DATE else "pre_kpang"
        weekday = (day.weekday() + 1) % 7  # Python Mon=0 -> JS Sun=0 convention
        for fuel in FUELS:
            series_by_station = reconstruct_day(path, fuel, last_price[fuel])
            reg = acc[fuel][regime]
            for uuid, series in series_by_station.items():
                reg.add_station_day(plz1.get(uuid, "x"), series, weekday)
        processed += 1
        log(f"  {day} [{regime}] done ({processed})")

    if processed == 0:
        raise SystemExit("No day files processed — check --data path and --window/--end.")

    log("Assembling curve.json ...")
    doc = {
        "_comment": "Generated by tools/build_curve.py from Tankerkoenig historical "
                    "data (CC BY-NC-SA 4.0). Do not edit by hand.",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "window_days": args.window,
        "schema_version": 1,
        "regimes": {},
    }
    for fuel in FUELS:
        doc["regimes"][fuel] = {}
        for regime in ("post_kpang", "pre_kpang"):
            reg = acc[fuel][regime]
            block = build_regime_json(reg, "overall")
            by_plz1 = {}
            for d in range(10):
                r = str(d)
                if reg.n_station_days[r] > 0:
                    b = build_regime_json(reg, r)
                    by_plz1[r] = {
                        "n_station_days": b["n_station_days"],
                        "overall": b["overall"],
                        "post_noon_decay": b["post_noon_decay"],
                    }
            block["by_plz1"] = by_plz1
            doc["regimes"][fuel][regime] = block

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"))
    total = sum(acc[f][r].n_station_days["overall"] for f in FUELS for r in ("post_kpang", "pre_kpang"))
    log(f"Wrote {args.out} ({total} station-days across all buckets).")


if __name__ == "__main__":
    main()
