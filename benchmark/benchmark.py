#!/usr/bin/env python3
"""
Benchmark the optimised e-commerce pipeline (Nov 2026).

Measures, at the default 58k rows and at 1M rows:
  * data/generate_data.py  (generate)
  * data/clean_data.py     (clean)
  * sql/validate_sqlite.py (SQL ETL + 7 dashboard views, SQLite mirror)
  * each of the 7 dashboard views, with the old single-column index set
    vs the new composite indexes (sql/schema.sql)

"Before" numbers are the pre-optimisation scripts measured 8 Nov 2026 on
this 4-vCPU host (same machine, same data sizes); they are recorded here
because the old scripts are superseded in the repo. "After" numbers are
measured live by this script (median of 3 runs at 58k, 2 runs at 1M).

  python3 benchmark/benchmark.py          # ~4-6 min, writes results.json
  python3 benchmark/benchmark.py --quick  # 58k scale only, ~1 min

1M-row intermediates live in benchmark/tmp/ and are deleted afterwards;
only benchmark/results.json is kept.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / "benchmark" / "tmp"
RESULTS = ROOT / "benchmark" / "results.json"

# Pre-optimisation timings (seconds), measured 8 Nov 2026 on this 4-vCPU
# host with the old scripts at the same data sizes. generate_old at 1M is
# a single timed run; the rest are medians of 3 (58k) / 1-2 (1M) runs.
BASELINE = {
    "generate_58k": 2.88, "clean_58k": 1.72, "validate_58k": 3.62,
    "generate_1m": 31.0, "clean_1m": 24.45,
}

VIEWS = ["vw_monthly_revenue_by_region", "vw_top_products",
         "vw_customer_demographics", "vw_yoy_growth", "vw_category_share",
         "vw_payment_method_mix", "vw_discount_impact"]


def run(cmd, reps=3):
    """Run cmd `reps` times; return (median seconds, peak RSS in MB).

    Peak RSS comes from os.wait4's rusage for the child — the max resident
    set of that specific process, not a machine-wide number.
    """
    times, peak_rss = [], 0.0
    for _ in range(reps):
        t0 = time.perf_counter()
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        _, status, ru = os.wait4(proc.pid, 0)
        dt = time.perf_counter() - t0
        if status != 0:
            raise RuntimeError(f"{' '.join(cmd)} failed (status {status})")
        times.append(dt)
        peak_rss = max(peak_rss, ru.ru_maxrss / 1024)  # KB -> MB on Linux
    return statistics.median(times), peak_rss


def time_views(raw_csv, clean_csv, composite, reps=3):
    """Median per-view query time (seconds) in a fresh in-memory SQLite DB.

    Imports sql/validate_sqlite.py's build_db so the views run against the
    exact committed logic, with either index set.
    """
    sys.path.insert(0, str(ROOT / "sql"))
    import validate_sqlite
    con, _ = validate_sqlite.build_db(raw_csv=raw_csv, clean_csv=clean_csv,
                                      composite_indexes=composite)
    cur = con.cursor()
    out = {}
    for v in VIEWS:
        ts = []
        for _ in range(reps):
            t0 = time.perf_counter()
            cur.execute(f"SELECT COUNT(*) FROM (SELECT * FROM {v})").fetchone()
            ts.append(time.perf_counter() - t0)
        out[v] = statistics.median(ts)
    con.close()
    return out


def main():
    ap = argparse.ArgumentParser(description="Benchmark the pipeline.")
    ap.add_argument("--quick", action="store_true",
                    help="58k scale only")
    args = ap.parse_args()
    TMP.mkdir(parents=True, exist_ok=True)
    results = {"baseline": BASELINE, "measured": {}, "views": {}}
    try:
        # ---- 58k scale ------------------------------------------------
        raw58, clean58 = TMP / "raw_58k.csv", TMP / "clean_58k.csv"
        t, rss = run([sys.executable, str(ROOT / "data" / "generate_data.py"),
                      "--out", str(raw58)])
        results["measured"]["generate_58k"] = {"s": round(t, 2), "peak_rss_mb": round(rss)}
        print(f"generate 58k: {t:.2f}s (was {BASELINE['generate_58k']}s)")
        t, rss = run([sys.executable, str(ROOT / "data" / "clean_data.py"),
                      "--raw", str(raw58), "--out", str(clean58)])
        results["measured"]["clean_58k"] = {"s": round(t, 2), "peak_rss_mb": round(rss)}
        print(f"clean 58k:    {t:.2f}s (was {BASELINE['clean_58k']}s)")
        t, rss = run([sys.executable, str(ROOT / "sql" / "validate_sqlite.py"),
                      "--raw", str(raw58), "--clean", str(clean58)])
        results["measured"]["validate_58k"] = {"s": round(t, 2), "peak_rss_mb": round(rss)}
        print(f"validate 58k: {t:.2f}s (was {BASELINE['validate_58k']}s)")

        print("views 58k (new vs old indexes)...")
        v_new = time_views(raw58, clean58, composite=True)
        v_old = time_views(raw58, clean58, composite=False)
        results["views"]["58k"] = {"composite": v_new, "single_col": v_old}

        if not args.quick:
            # ---- 1M scale ---------------------------------------------
            raw1m, clean1m = TMP / "raw_1m.csv", TMP / "clean_1m.csv"
            t, rss = run([sys.executable, str(ROOT / "data" / "generate_data.py"),
                          "--base-rows", "1000000", "--out", str(raw1m)], reps=2)
            results["measured"]["generate_1m"] = {"s": round(t, 2), "peak_rss_mb": round(rss)}
            print(f"generate 1M:  {t:.2f}s (was ~{BASELINE['generate_1m']}s)")
            t, rss = run([sys.executable, str(ROOT / "data" / "clean_data.py"),
                          "--raw", str(raw1m), "--out", str(clean1m)], reps=2)
            results["measured"]["clean_1m"] = {"s": round(t, 2), "peak_rss_mb": round(rss)}
            print(f"clean 1M:     {t:.2f}s (was {BASELINE['clean_1m']}s)")
            t, rss = run([sys.executable, str(ROOT / "sql" / "validate_sqlite.py"),
                          "--raw", str(raw1m), "--clean", str(clean1m)], reps=1)
            results["measured"]["validate_1m"] = {"s": round(t, 2), "peak_rss_mb": round(rss)}
            print(f"validate 1M:  {t:.2f}s (no baseline — new capability)")

            print("views 1M (new vs old indexes)...")
            v_new = time_views(raw1m, clean1m, composite=True)
            v_old = time_views(raw1m, clean1m, composite=False)
            results["views"]["1m"] = {"composite": v_new, "single_col": v_old}

        RESULTS.write_text(json.dumps(results, indent=2))
        print(f"\nWrote {RESULTS}")
        m = results["measured"]
        for k in ("generate_58k", "clean_58k", "validate_58k",
                  "generate_1m", "clean_1m"):
            if k in m and k in BASELINE:
                print(f"  {k}: {BASELINE[k]}s -> {m[k]['s']}s "
                      f"({BASELINE[k] / m[k]['s']:.1f}x faster)")
        for scale in results["views"]:
            tot_new = sum(results["views"][scale]["composite"].values())
            tot_old = sum(results["views"][scale]["single_col"].values())
            print(f"  views {scale} total: {tot_old:.3f}s -> {tot_new:.3f}s "
                  f"({tot_old / tot_new:.1f}x faster)")
    finally:
        for f in TMP.glob("*.csv"):
            f.unlink()
        print("Cleaned up benchmark/tmp/*.csv")


if __name__ == "__main__":
    main()
