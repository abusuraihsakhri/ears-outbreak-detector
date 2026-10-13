# EARS Outbreak Detector

Daily count aberration detection using Early Aberration Reporting System (EARS) C1, C2 and C3 statistics. Includes a browser-only analyzer, Python command-line implementation, and separate experimental FastAPI audit service.

## Browser application

The static application is in [web/](web/). Upload or paste a CSV with `date,count` columns, select a baseline window and alert thresholds, run the analysis, inspect count trajectories and flagged dates, and export full results or alerts as CSV.

No account or backend is needed. Files and calculations remain in the browser; the page does not send them to a server, store them in browser storage, or load third-party libraries. A live link will be added after deployment has been verified.

## Statistical methods

Each daily count is compared against the sample mean and standard deviation of a trailing baseline:

- **C1:** rolling seven-day baseline without a gap, by default.
- **C2:** same baseline with a two-day exclusion gap, by default.
- **C3:** sum of `max(0, C2(t−i) − 1)` for the current and preceding two days (i = 0, 1, 2).

Default alerts are **C1 > 3**, **C2 > 3**, and **C3 > 2**. Window length (7, 14, or 28 days), C2 gap and alert thresholds are configurable. Optional day-of-week adjustment selects matching weekdays in the baseline; at least two matching observations are required for sample SD.

Flat baselines receive a finite statistic of 100 when the current count increases and 0 otherwise. Initial days without sufficient baseline history are unscored. Missing calendar dates between observations are filled with zero, a modeling assumption that must be justified from the surveillance process.

These statistics flag **unusual counts**, not verified outbreaks. Performance depends on reporting patterns, data quality, seasonality, baseline length and threshold choices. Clinical/public-health escalation requires independent review.

References: [CDC MMWR EARS evaluation](https://www.cdc.gov/MMWR/preview/mmwrhtml/su5401a20.htm) and [comparison of aberration detection methods](https://pmc.ncbi.nlm.nih.gov/articles/PMC6736430/).

## Input format

Provide a CSV containing ISO calendar dates and nonnegative whole-number daily counts:

```csv
date,count
2026-01-01,10
2026-01-02,12
2026-01-03,11
```

Dates must be unique. Missing, negative, fractional and nonfinite counts are rejected. The browser accepts files up to 2 MB and date spans of up to 50,000 days; the Python loader also supports custom date and count column names.

## Python CLI

Requires Python 3.10 or newer. From the repository root:

```bash
python -m pip install -e ".[dev]"
python ears.py scan --input sample_data.csv
python ears.py compare --input sample_data.csv
python ears.py plot --input sample_data.csv --out plot.png
python ears.py scan --input sample_data.csv --window 14 --gap 2 --threshold 3 --c3-threshold 2
python -m pytest -q
```

The CLI supports `--dow-adjust`, custom `--date-col` and `--count-col` names, and `--out` for scan CSV reports. The comparison command reports alert counts and overlap, **not** sensitivity without ground-truth outbreak labels.

## Separate agent audit API (experimental)

This generic threshold-based worker service is separate from the EARS statistics. It is **not** a validated outbreak classifier or clinical decision-support system.

```bash
python cli.py audit --task-id TASK-001 --primary 28.5 --secondary 14.2
python cli.py verify-audit
python cli.py serve --host 127.0.0.1 --port 8000
```

Endpoints: `/health`, `/metrics`, `/api/audit`, `/api/chat`, and `/api/audit/logs`. Chat currently uses a deterministic mock rather than a real external model. The metrics endpoint returns JSON, not Prometheus exposition format.

The in-memory ledger uses HMAC-SHA256 chained signatures and verifies each signature. Set `AUDIT_SECRET_KEY` for a persistent signing key. The ledger itself is **not persisted** across restarts and is not a regulated audit retention system. Regex-based identifier checks are incomplete safeguards and **do not establish HIPAA compliance**. Do not submit identifiable clinical records. Restrict API access to trusted environments.

Run using Docker Compose with a unique secret:

```bash
export AUDIT_SECRET_KEY='replace-with-a-long-random-secret'
docker compose up --build
```

## Technology, testing and deployment

The web application uses HTML, CSS, JavaScript and SVG without dependencies. Current evergreen browsers are targeted; cross-browser testing beyond the numerical automated tests has not been established. Python uses NumPy, pandas and matplotlib, and the agent service uses FastAPI and Pydantic.

GitHub Actions tests Python 3.10, 3.11 and 3.12, checks browser JavaScript syntax and executes Node numerical regression tests. A Pages workflow deploys the static page from `web/`.

## License

MIT — see [LICENSE](LICENSE).
