# Ears Outbreak Detector

> **Domain:** Infectious Disease Surveillance & Microbiology  
> **Reference Guidelines & Standards:** `CLSI M100, EUCAST & CDC NHSN Clinical Standards`

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB.svg?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg?logo=fastapi&logoColor=white)
![Audit Trail](https://img.shields.io/badge/Audit-HMAC--SHA256_Tamper--Evident-brightgreen.svg)
![Zero-PHI Guard](https://img.shields.io/badge/Guard-Zero--PHI_Outbound-blue.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker&logoColor=white)

</div>

---

## 📖 What It Does

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
C3: a short cumulative-sum statistic that combines the current and two
    prior C2 values, giving it more sensitivity to a sustained, gradual
    increase than C1/C2 alone:

        C3(t) = max(0, C2(t) + C2(t-1) + C2(t-2) - 3)

An aberration is flagged when a C statistic exceeds a configurable
threshold (typically 3).

---

## ⚙️ Key Capabilities & Algorithmic Modules

### 🔬 Analytical Functions

- **`load_daily_series()`**: Read a CSV of (date, count) rows and return a complete daily series.

Any missing calendar dates between the first and last observed date are
inserted with a count of 0, since the EARS baseline windows assume a
contiguous daily series.
- **`compute_c3()`**: C3(t) = max(0, C2(t) + C2(t-1) + C2(t-2) - 3).
- **`compute_ears()`**: Compute C1, C2, C3 and alert flags for every day in `df`.

df must have 'date' and 'count' columns (see load_daily_series).
- **`scan_report()`**: Return only the rows flagged as an aberration by the chosen method(s).
- **`compare_methods()`**: Summarize alert counts and overlap between C1, C2, and C3.

---

## 💻 CLI Quickstart & Usage

### 1. Guided Interactive Mode
```bash
python cli.py
```

### 2. Direct Parameterized Evaluation
```bash
python cli.py --task-id <value> --target <value> --primary <value> --secondary <value>
```

### Parameter Reference
- `--task-id`: Specifies input measurement or parameter value.
- `--target`: Specifies input measurement or parameter value.
- `--primary`: Specifies input measurement or parameter value.
- `--secondary`: Specifies input measurement or parameter value.
- `--critical`: Specifies input measurement or parameter value.
- `--status`: Specifies input measurement or parameter value.
- `--input`: Specifies input measurement or parameter value.
- `--output`: Specifies input measurement or parameter value.

### Input Data Schema

| Field | Description | Requirement |
|:------|:------------|:------------|
| `suite_name` | Parameter / observation metric | Required |
| `system_slug` | Parameter / observation metric | Required |
| `standard_reference` | Parameter / observation metric | Required |
| `test_cases` | Parameter / observation metric | Required |

---

## 🛡️ Security & Enterprise Architecture

* **Zero-PHI Outbound Interceptor:** Active AST and regex inspection blocking SSNs, MRNs, phone numbers, and patient identifiers.
* **Tamper-Evident HMAC-SHA256 Audit Trail:** Chained, cryptographically signed logs for every evaluation and state transition.
* **Air-Gapped LLM Reasoning Adapter:** Agnostic integration for local Ollama instances (`llama3`, `mistral`), Claude 3.5 Sonnet, GPT-4o, and deterministic test mocks.
* **Active Learning Bayesian Calibration:** Dynamic tracker updating worker reliability weights and monitoring Brier calibration drift.
* **FastAPI & Prometheus Telemetry:** Exposes OpenAPI 3.1 REST endpoints and operational Prometheus metrics (`/metrics`).

---

## 🧪 Testing & Verification

Run the automated test suite:

```bash
pytest -v
```

Execute high-throughput batch simulation benchmarks:

```bash
python simulator.py --tasks 1000 --concurrency 8
```

---

## 🐳 Container Deployment

```bash
docker build -t ears-outbreak-detector .
docker run -p 8000:8000 ears-outbreak-detector
```
