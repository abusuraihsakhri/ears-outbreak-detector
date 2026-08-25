"""Tests for the EARS outbreak detector core algorithm (stdlib unittest)."""

import statistics
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import ears


def make_df(dates, counts):
    return pd.DataFrame({"date": pd.to_datetime(dates), "count": counts})


class TestCStat(unittest.TestCase):
    def test_c1_flags_spike_over_flat_baseline(self):
        # 7 flat baseline days, then a clear spike. SD of the flat baseline
        # is 0, so the implementation must fall back to the CAP sentinel
        # rather than raising a divide-by-zero error.
        dates = pd.date_range("2026-01-01", periods=8, freq="D")
        counts = [10, 10, 10, 10, 10, 10, 10, 30]
        df = make_df(dates, counts)

        result = ears.compute_ears(df, window=7, gap=2, threshold=3.0, dow_adjust=False)
        last = result.iloc[-1]

        self.assertEqual(last["C1"], ears.CAP)
        self.assertTrue(bool(last["alert_C1"]))

    def test_c1_matches_hand_computed_zscore(self):
        # Baseline with real variance; cross-check against an independent
        # (non-numpy) computation of the mean/sample-stdev z-score.
        baseline = [8, 10, 12, 9, 11, 10, 9]
        test_value = 20
        dates = pd.date_range("2026-02-01", periods=8, freq="D")
        counts = baseline + [test_value]
        df = make_df(dates, counts)

        result = ears.compute_ears(df, window=7, gap=0, threshold=3.0, dow_adjust=False)
        c1_last = result.iloc[-1]["C1"]

        expected_mean = statistics.mean(baseline)
        expected_sd = statistics.stdev(baseline)  # sample stdev, ddof=1
        expected_c1 = (test_value - expected_mean) / expected_sd

        self.assertAlmostEqual(c1_last, expected_c1, places=9)

    def test_c1_nan_when_insufficient_history(self):
        dates = pd.date_range("2026-03-01", periods=5, freq="D")
        counts = [5, 6, 7, 8, 9]
        df = make_df(dates, counts)

        result = ears.compute_ears(df, window=7, gap=2, threshold=3.0, dow_adjust=False)
        # Not enough trailing history anywhere in a 5-day series with a 7-day window.
        self.assertTrue(result["C1"].isna().all())


class TestC2GuardBand(unittest.TestCase):
    def test_c2_excludes_guard_band_days(self):
        # 7-day flat baseline of 10s, then a 2-day guard band with an
        # anomalous value (50) that C2 must NOT use, then the test day.
        dates = pd.date_range("2026-04-01", periods=10, freq="D")
        counts = [10, 10, 10, 10, 10, 10, 10, 50, 50, 12]
        df = make_df(dates, counts)

        result = ears.compute_ears(df, window=7, gap=2, threshold=3.0, dow_adjust=False)
        last = result.iloc[-1]

        # Baseline for C2 is the first 7 flat 10s (mean=10, sd=0); the guard
        # band's 50s are excluded, so a mild count of 12 should still flag.
        self.assertEqual(last["C2"], ears.CAP)
        self.assertTrue(bool(last["alert_C2"]))

        # C1's baseline (no gap) DOES include the two 50s, pulling the mean
        # up enough that the same test day (12) should not be flagged by C1.
        self.assertFalse(bool(last["alert_C1"]))


class TestC3Cusum(unittest.TestCase):
    def test_c3_formula_direct(self):
        c2 = np.array([1.0, 2.0, 0.5, np.nan, 4.0, 4.0, 4.0])
        c3 = ears.compute_c3(c2)

        # index 2: max(0, 1.0+2.0+0.5-3) = 0.5
        self.assertAlmostEqual(c3[2], 0.5, places=9)
        # index 3 depends on a NaN input -> NaN
        self.assertTrue(np.isnan(c3[3]))
        # index 6: max(0, 4+4+4-3) = 9
        self.assertAlmostEqual(c3[6], 9.0, places=9)
        # indices 0,1 always NaN (not enough history for a 3-day sum)
        self.assertTrue(np.isnan(c3[0]))
        self.assertTrue(np.isnan(c3[1]))

    def test_c3_accumulates_sustained_mild_elevation(self):
        # A sustained mild elevation that individually never trips C1/C2
        # (threshold 3) should still accumulate into a C3 alert.
        dates = pd.date_range("2026-05-01", periods=13, freq="D")
        baseline = [10, 10, 10, 10, 10, 10, 10]
        mild_rise = [10, 10, 15, 15, 15, 15]  # gap of 2 days then 4 mildly elevated days
        counts = baseline + mild_rise
        df = make_df(dates, counts)

        result = ears.compute_ears(df, window=7, gap=2, threshold=3.0, dow_adjust=False)

        self.assertGreater(result.iloc[-1]["C3"], result.iloc[-1]["C2"])


class TestDayOfWeekAdjustment(unittest.TestCase):
    def test_dow_adjust_baseline_matches_manual_weekday_filter(self):
        # 31 days: a 28-day baseline span (indices 0..27, exactly 4 full
        # weeks so every weekday appears exactly 4 times), a 2-day guard
        # band (28..29), and a test day at index 30. The days sharing the
        # test day's weekday within the baseline span get varying counts
        # (so the baseline has real variance); every other day is flat.
        dates = pd.date_range("2026-01-01", periods=31, freq="D")
        weekday_arr = dates.weekday.to_numpy()
        target_wd = weekday_arr[-1]

        counts = [10.0] * 31
        same_wd_in_span = [i for i in range(0, 28) if weekday_arr[i] == target_wd]
        self.assertEqual(len(same_wd_in_span), 4)  # sanity check: 4 full weeks
        for i, v in zip(same_wd_in_span, [28.0, 30.0, 32.0, 34.0]):
            counts[i] = v
        counts[-1] = 40.0  # test day

        df = make_df(dates, counts)

        result_dow = ears.compute_ears(df, window=28, gap=2, threshold=3.0, dow_adjust=True)
        result_plain = ears.compute_ears(df, window=28, gap=2, threshold=3.0, dow_adjust=False)

        # Cross-check the dow-adjusted C2 against an independent computation
        # of the mean/sample-stdev over only the matching-weekday baseline days.
        expected_mean = statistics.mean([28.0, 30.0, 32.0, 34.0])
        expected_sd = statistics.stdev([28.0, 30.0, 32.0, 34.0])
        expected_c2 = (40.0 - expected_mean) / expected_sd
        self.assertAlmostEqual(result_dow.iloc[-1]["C2"], expected_c2, places=9)

        # The unadjusted baseline mixes in the 24 flat days of 10, pulling
        # the mean far below the dow-adjusted mean -> a different C2 value.
        self.assertNotAlmostEqual(result_dow.iloc[-1]["C2"], result_plain.iloc[-1]["C2"], places=3)


class TestLoadDailySeries(unittest.TestCase):
    def test_fills_missing_calendar_dates_with_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "data.csv"
            csv_path.write_text("date,count\n2026-01-01,5\n2026-01-04,7\n")

            df = ears.load_daily_series(str(csv_path))

            self.assertEqual(len(df), 4)  # Jan 1,2,3,4
            self.assertEqual(df.loc[df["date"] == "2026-01-02", "count"].iloc[0], 0.0)
            self.assertEqual(df.loc[df["date"] == "2026-01-03", "count"].iloc[0], 0.0)
            self.assertEqual(df.loc[df["date"] == "2026-01-04", "count"].iloc[0], 7.0)

    def test_missing_column_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "bad.csv"
            csv_path.write_text("day,cases\n2026-01-01,5\n")
            with self.assertRaises(ValueError):
                ears.load_daily_series(str(csv_path))


class TestReportAndCompare(unittest.TestCase):
    def test_scan_report_and_compare_methods(self):
        dates = pd.date_range("2026-07-01", periods=10, freq="D")
        counts = [10, 10, 10, 10, 10, 10, 10, 10, 10, 40]
        df = make_df(dates, counts)

        result = ears.compute_ears(df, window=7, gap=2, threshold=3.0, dow_adjust=False)

        report = ears.scan_report(result, method="all")
        self.assertEqual(len(report), 1)
        self.assertEqual(report.iloc[0]["count"], 40)

        summary = ears.compare_methods(result)
        self.assertEqual(summary["C1"]["n_alerts"], 1)
        self.assertIn(dates[-1].strftime("%Y-%m-%d"), summary["union_any"])


if __name__ == "__main__":
    unittest.main()
