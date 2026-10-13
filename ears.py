"""
EARS Outbreak Detector

Implements the CDC EARS (Early Aberration Reporting System) C1, C2, and C3
aberration-detection statistics for daily syndromic surveillance counts, as
described by Hutwagner et al. (2003), "The Bioterrorism Preparedness and
Response Early Aberration Reporting System (EARS)".

For a test day t with observed count X(t):

    C(t) = (X(t) - mean_baseline) / sd_baseline

C1: baseline is the trailing `window` days immediately before t (no gap).
C2: baseline is the trailing `window` days before t, separated from t by a
    `gap`-day guard band (default 2 days), so recent case counts cannot
    leak into (and inflate) the current baseline.
C3: sum of positive deviations from 1 SD across the current and two
    preceding C2 values:

        C3(t) = sum(max(0, C2(t-i) - 1) for i in (0, 1, 2))

An aberration is flagged when C1/C2 exceeds 3, or C3 exceeds 2,
by default. Each threshold can be configured.
"""

import argparse
import sys

import numpy as np
import pandas as pd

# Sentinel finite value used in place of +inf when the baseline standard
# deviation is 0 (a perfectly flat baseline) and the observed count exceeds
# the baseline mean. Any realistic threshold is far below this, so the day
# is still correctly flagged, without propagating actual infinities through
# arithmetic and plotting.
CAP = 100.0

METHODS = ("C1", "C2", "C3")


def load_daily_series(csv_path, date_col="date", count_col="count"):
    """Read a CSV of (date, count) rows and return a complete daily series.

    Any missing calendar dates between the first and last observed date are
    inserted with a count of 0, since the EARS baseline windows assume a
    contiguous daily series.
    """
    df = pd.read_csv(csv_path)
    if date_col not in df.columns or count_col not in df.columns:
        raise ValueError(
            f"CSV must contain columns '{date_col}' and '{count_col}'. "
            f"Found: {list(df.columns)}"
        )

    if df.empty:
        raise ValueError("Input CSV must contain at least one observation.")
    df[date_col] = pd.to_datetime(df[date_col], errors="raise")
    if df[date_col].isna().any() or not (df[date_col] == df[date_col].dt.normalize()).all():
        raise ValueError("Dates must be valid calendar dates without time components.")
    df[count_col] = pd.to_numeric(df[count_col], errors="raise")
    values = df[count_col].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any() or (values % 1 != 0).any():
        raise ValueError("Counts must be finite, nonnegative whole numbers.")
    df = df[[date_col, count_col]].sort_values(date_col).reset_index(drop=True)

    if df[date_col].duplicated().any():
        raise ValueError("Duplicate dates found in input CSV; each date must appear once.")

    full_range = pd.date_range(df[date_col].min(), df[date_col].max(), freq="D")
    full = pd.DataFrame({date_col: full_range})
    merged = full.merge(df, on=date_col, how="left")

    n_missing = int(merged[count_col].isna().sum())
    if n_missing:
        print(
            f"Warning: {n_missing} missing date(s) in the input series were filled with 0 counts.",
            file=sys.stderr,
        )
    merged[count_col] = merged[count_col].fillna(0.0)

    merged = merged.rename(columns={date_col: "date", count_col: "count"})
    return merged


def _baseline_indices(t, window, gap, weekday, dow_adjust):
    """Row indices making up the baseline for test-day index t.

    The baseline spans the `window` calendar days ending `gap` days before
    t. With day-of-week adjustment enabled, only the days within that span
    that share t's weekday are kept, so seasonal/weekly reporting patterns
    (e.g. lower ED visit counts on weekends) don't bias the baseline.
    """
    lo = t - gap - window
    hi = t - gap  # exclusive
    if lo < 0:
        return None
    idx = list(range(lo, hi))
    if dow_adjust:
        idx = [i for i in idx if weekday[i] == weekday[t]]
    return idx


def _c_stat(counts, weekday, window, gap, dow_adjust):
    """Compute a C1/C2-style statistic for every day in the series."""
    n = len(counts)
    c = np.full(n, np.nan)
    for t in range(n):
        idx = _baseline_indices(t, window, gap, weekday, dow_adjust)
        if idx is None or len(idx) < 2:
            continue  # not enough baseline history to estimate a standard deviation
        baseline = counts[idx]
        mean_b = baseline.mean()
        sd_b = baseline.std(ddof=1)
        x = counts[t]
        if sd_b == 0:
            c[t] = 0.0 if x <= mean_b else CAP
        else:
            c[t] = (x - mean_b) / sd_b
    return c


def compute_c3(c2):
    """C3(t) = sum(max(0, C2(t-i) - 1) for i in (0, 1, 2))."""
    n = len(c2)
    c3 = np.full(n, np.nan)
    for t in range(n):
        if t < 2:
            continue
        window_vals = c2[t - 2 : t + 1]
        if np.any(np.isnan(window_vals)):
            continue
        c3[t] = float(np.maximum(0.0, window_vals - 1.0).sum())
    return c3


def compute_ears(df, window=7, gap=2, threshold=3.0, dow_adjust=False, c3_threshold=2.0):
    """Compute C1, C2, C3 and alert flags for every day in `df`.

    df must have 'date' and 'count' columns (see load_daily_series).
    """
    if not isinstance(window, int) or window < 2:
        raise ValueError("window must be an integer of at least 2 days.")
    if not isinstance(gap, int) or gap < 0:
        raise ValueError("gap must be a nonnegative integer.")
    if not np.isfinite(threshold) or not 0 <= threshold < CAP:
        raise ValueError(f"threshold must be finite and within [0, {CAP}).")
    if not np.isfinite(c3_threshold) or not 0 <= c3_threshold < CAP * 3:
        raise ValueError("c3_threshold must be finite and nonnegative.")
    if df.empty or not {"date", "count"}.issubset(df.columns):
        raise ValueError("Input must contain at least one date and count.")
    dates = pd.to_datetime(df["date"], errors="raise")
    if dates.isna().any() or not (dates == dates.dt.normalize()).all():
        raise ValueError("Dates must be valid calendar dates.")
    if dates.duplicated().any() or not dates.is_monotonic_increasing or (
        len(dates) > 1 and not (dates.diff().iloc[1:] == pd.Timedelta(days=1)).all()
    ):
        raise ValueError("Input must have unique, consecutive dates in ascending order.")
    counts = pd.to_numeric(df["count"], errors="raise").to_numpy(dtype=float)
    if not np.isfinite(counts).all() or (counts < 0).any() or (counts % 1 != 0).any():
        raise ValueError("Counts must be finite, nonnegative whole numbers.")
    weekday = dates.dt.weekday.to_numpy()

    c1 = _c_stat(counts, weekday, window=window, gap=0, dow_adjust=dow_adjust)
    c2 = _c_stat(counts, weekday, window=window, gap=gap, dow_adjust=dow_adjust)
    c3 = compute_c3(c2)

    out = df.copy()
    out["C1"], out["C2"], out["C3"] = c1, c2, c3
    for m in METHODS:
        out[f"alert_{m}"] = out[m] > (c3_threshold if m == "C3" else threshold)
    return out


def scan_report(result_df, method="all"):
    """Return only the rows flagged as an aberration by the chosen method(s)."""
    methods = list(METHODS) if method == "all" else [method.upper()]
    any_alert = np.zeros(len(result_df), dtype=bool)
    for m in methods:
        any_alert |= result_df[f"alert_{m}"].fillna(False).to_numpy()
    cols = ["date", "count"] + list(METHODS) + [f"alert_{m}" for m in METHODS]
    return result_df.loc[any_alert, cols].copy()


def compare_methods(result_df):
    """Summarize alert counts and overlap between C1, C2, and C3."""
    per_method = {}
    date_sets = {}
    for m in METHODS:
        alerts = result_df[f"alert_{m}"].fillna(False)
        dates = result_df.loc[alerts, "date"].dt.strftime("%Y-%m-%d").tolist()
        per_method[m] = {
            "n_alerts": int(alerts.sum()),
            "alert_rate": float(alerts.mean()),
            "dates": dates,
        }
        date_sets[m] = set(dates)

    overlap_all = sorted(date_sets["C1"] & date_sets["C2"] & date_sets["C3"])
    union_any = sorted(date_sets["C1"] | date_sets["C2"] | date_sets["C3"])

    return {
        **per_method,
        "overlap_all_three": overlap_all,
        "union_any": union_any,
    }


def plot_ears(result_df, methods, out_path):
    """Plot the observed count series with each method's flagged days highlighted."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(result_df["date"], result_df["count"], color="steelblue", linewidth=1.2, label="Observed count")

    colors = {"C1": "#e69138", "C2": "#38761d", "C3": "#cc0000"}
    markers = {"C1": "^", "C2": "s", "C3": "o"}

    for m in methods:
        flagged = result_df[result_df[f"alert_{m}"].fillna(False)]
        if len(flagged):
            ax.scatter(
                flagged["date"],
                flagged["count"],
                color=colors[m],
                marker=markers[m],
                s=70,
                label=f"{m} alert",
                zorder=5,
                edgecolor="black",
                linewidth=0.5,
            )

    ax.set_xlabel("Date")
    ax.set_ylabel("Daily count")
    ax.set_title("EARS outbreak detection")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _add_common_args(p):
    p.add_argument("--input", required=True, help="Path to input CSV with date and count columns.")
    p.add_argument("--date-col", default="date", help="Name of the date column (default: date).")
    p.add_argument("--count-col", default="count", help="Name of the daily count column (default: count).")
    p.add_argument(
        "--window", type=int, default=7, choices=(7, 14, 28),
        help="Baseline window length in days: 7, 14, or 28 (default: 7).",
    )
    p.add_argument(
        "--gap", type=int, default=2,
        help="Guard-band gap in days before the test day for the C2/C3 baseline (default: 2). C1 always uses no gap.",
    )
    p.add_argument("--threshold", type=float, default=3.0, help="C1/C2 alert threshold (default: 3.0).")
    p.add_argument("--c3-threshold", type=float, default=2.0, help="C3 alert threshold (default: 2.0).")
    p.add_argument(
        "--dow-adjust", action="store_true",
        help="Restrict the baseline to days sharing the test day's weekday, to control for weekly reporting patterns.",
    )


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ears.py",
        description="CDC EARS (C1/C2/C3) outbreak aberration detector for daily syndromic surveillance counts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Batch scan a time series and report flagged (aberrant) dates.")
    _add_common_args(p_scan)
    p_scan.add_argument("--method", default="all", choices=("all", "c1", "c2", "c3"), help="Which method(s) to report (default: all).")
    p_scan.add_argument("--out", default=None, help="Optional path to write the flagged-date report as CSV.")

    p_cmp = sub.add_parser("compare", help="Compare alert sensitivity across C1, C2, and C3 on the same data.")
    _add_common_args(p_cmp)

    p_plot = sub.add_parser("plot", help="Plot the count series with flagged aberrations highlighted.")
    _add_common_args(p_plot)
    p_plot.add_argument("--method", default="all", choices=("all", "c1", "c2", "c3"), help="Which method(s) to highlight (default: all).")
    p_plot.add_argument("--out", required=True, help="Output image path (e.g. plot.png).")

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    df = load_daily_series(args.input, args.date_col, args.count_col)
    result = compute_ears(df, window=args.window, gap=args.gap, threshold=args.threshold, dow_adjust=args.dow_adjust, c3_threshold=args.c3_threshold)

    if args.command == "scan":
        report = scan_report(result, method=args.method)
        if report.empty:
            print("No aberrations flagged.")
        else:
            printable = report.copy()
            printable["date"] = printable["date"].dt.strftime("%Y-%m-%d")
            with pd.option_context("display.max_rows", None, "display.width", 120):
                print(printable.to_string(index=False))
        if args.out:
            report.to_csv(args.out, index=False)
            print(f"Report written to {args.out}")

    elif args.command == "compare":
        summary = compare_methods(result)
        print("Sensitivity comparison (same data, same threshold):")
        for m in METHODS:
            s = summary[m]
            print(f"  {m}: {s['n_alerts']} alert(s) ({s['alert_rate'] * 100:.1f}% of days)")
        print(f"Flagged by all three methods: {len(summary['overlap_all_three'])} date(s): {summary['overlap_all_three']}")
        print(f"Flagged by at least one method: {len(summary['union_any'])} date(s): {summary['union_any']}")

    elif args.command == "plot":
        methods = list(METHODS) if args.method == "all" else [args.method.upper()]
        plot_ears(result, methods, args.out)
        print(f"Plot saved to {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
