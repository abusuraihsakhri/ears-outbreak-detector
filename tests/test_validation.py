"""Validation and audit-integrity regression tests."""
import numpy as np
import pandas as pd
import pytest

from agents.base import AuditTrail, SecurityException
from ears import compute_ears, load_daily_series


@pytest.mark.parametrize("counts", [
    ["5", "-1"], ["1", "3.5"], ["NaN", "2"], ["Infinity", "5"], ["", "2"]
])
def test_rejects_invalid_csv_counts(tmp_path, counts):
    path = tmp_path / "counts.csv"
    path.write_text("date,count\n2026-01-01," + counts[0] +
                    "\n2026-01-02," + counts[1] + "\n")
    with pytest.raises(ValueError):
        load_daily_series(path)


def test_rejects_empty_csv(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("date,count\n")
    with pytest.raises(ValueError, match="at least one"):
        load_daily_series(path)


def test_rejects_noncontiguous_and_unsorted_input():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01", "2026-01-03"]),
        "count": [3, 4],
    })
    with pytest.raises(ValueError, match="consecutive"):
        compute_ears(df)


@pytest.mark.parametrize("gap,window,threshold", [
    (-1, 7, 3), (2, 0, 3), (2, 7, float("nan")),
    (2, 7, float("inf")), (2, 7, 100),
])
def test_invalid_analysis_parameters(gap, window, threshold):
    df = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=12),
                       "count": np.arange(12)})
    with pytest.raises(ValueError):
        compute_ears(df, gap=gap, window=window, threshold=threshold)


def test_audit_integrity_detects_rewritten_payload_hash():
    audit = AuditTrail(secret_key="test-secret")
    audit.log("operator", "system", "SCAN", {"n": 12})
    audit.log("operator", "system", "SCAN", {"n": 13})
    assert audit.verify_integrity()
    audit.logs[0]["payload_hash"] = "0" * 64
    assert not audit.verify_integrity()


def test_audit_integrity_detects_rewritten_signature():
    audit = AuditTrail(secret_key="test-secret")
    audit.log("operator", "system", "SCAN", {"n": 12})
    audit.logs[0]["current_hash"] = "0" * 64
    assert not audit.verify_integrity()


def test_public_audit_trail_is_defensive_copy():
    audit = AuditTrail(secret_key="test-secret")
    audit.log("operator", "system", "SCAN", {"n": 12})
    public = audit.get_trail()
    public[0]["actor"] = "attacker"
    assert audit.verify_integrity()
    assert audit.get_trail()[0]["actor"] == "operator"


def test_audit_metadata_is_screened_for_obvious_identifiers():
    audit = AuditTrail(secret_key="test-secret")
    with pytest.raises(SecurityException):
        audit.log("MRN-12345678", "system", "SCAN", {"n": 12})
