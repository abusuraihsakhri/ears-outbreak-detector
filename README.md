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

EARS Outbreak Detector implements the CDC EARS (Early Aberration Reporting System) C1, C2, and C3
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

### 🔬 Analytical Functions (ears.py)

- **`load_daily_series()`**: Read a CSV of (date, count) rows and return a complete daily series.
  Any missing calendar dates between the first and last observed date are
  inserted with a count of 0, since the EARS baseline windows assume a
  contiguous daily series.
- **`compute_c3()`**: C3(t) = max(0, C2(t) + C2(t-1) + C2(t-2) - 3).
- **`compute_ears()`**: Compute C1, C2, C3 and alert flags for every day in `df`.
- **`scan_report()`**: Return only the rows flagged as an aberration by the chosen method(s).
- **`compare_methods()`**: Summarize alert counts and overlap between C1, C2, and C3.

### 🤖 Multi-Agent Orchestration (agents/)

- **SystemSupervisor**: Coordinates specialized worker agents for task evaluation.
- **InvariantQCWorker**: Audits primary metric thresholds.
- **SafetyEscalationWorker**: Triggers on critical safety interlocks.
- **ProtocolConformanceWorker**: Detects protocol discordances.
- **PHIGuard**: Zero-PHI outbound interceptor blocking SSNs, MRNs, phone numbers, and patient identifiers.
- **AuditLogger**: Tamper-evident HMAC-SHA256 chained audit trail.

---

## 💻 CLI Quickstart & Usage

### 1. EARS Statistical Analysis

```bash
# Scan a time series for aberrations
python ears.py scan --input sample_data.csv

# Compare C1/C2/C3 sensitivity
python ears.py compare --input sample_data.csv

# Plot results
python ears.py plot --input sample_data.csv --out plot.png
```

### 2. Multi-Agent Task Evaluation

```bash
# Single task audit
python cli.py audit --task-id TASK-001 --primary 28.5 --secondary 14.2 --status DISCORDANT

# Batch process CSV records
python cli.py batch -i input.csv -o results.csv

# Verify audit trail integrity
python cli.py verify-audit

# Interactive chat
python cli.py chat "What is the current system status?"
```

### 3. Launch REST API Server

```bash
python cli.py serve --host 127.0.0.1 --port 8000
```

---

## 🛡️ Security & Enterprise Architecture

* **Zero-PHI Outbound Interceptor:** Active regex inspection blocking SSNs, MRNs, phone numbers, emails, DOBs, and patient names.
* **Tamper-Evident HMAC-SHA256 Audit Trail:** Chained, cryptographically signed logs for every evaluation and state transition.
* **Air-Gapped LLM Reasoning Adapter:** Agnostic integration for local Ollama instances (`llama3`, `mistral`), Claude 3.5 Sonnet, GPT-4o, and deterministic test mocks.
* **FastAPI & Prometheus Telemetry:** Exposes OpenAPI 3.1 REST endpoints and operational Prometheus metrics (`/metrics`).

---

## 🧪 Testing & Verification

Install development dependencies:

```bash
pip install -e ".[dev]"
```

Run the automated test suite:

```bash
pytest -v
```

Execute high-throughput batch simulation benchmarks:

```bash
python simulator.py 1000
```

---

## 🐳 Container Deployment

```bash
docker build -t ears-outbreak-detector .
docker run -p 8000:8000 -e AUDIT_SECRET_KEY=your-secret-key ears-outbreak-detector
```

Or using Docker Compose:

```bash
AUDIT_SECRET_KEY=your-secret-key docker compose up
```

---

## 📁 Project Structure

```
ears-outbreak-detector/
├── ears.py              # Core EARS C1/C2/C3 algorithm
├── cli.py               # Command-line interface
├── simulator.py         # High-throughput stress testing
├── test_ears.py         # Unit tests for core algorithm
├── sample_data.csv      # Example surveillance data
├── agents/
│   ├── __init__.py
│   ├── models.py        # Pydantic data models
│   ├── base.py          # PHI guard, audit logger, security
│   ├── supervisor.py    # Multi-agent orchestration
│   ├── workers.py       # Specialized domain workers
│   ├── llm_factory.py   # LLM provider abstraction
│   ├── api.py           # FastAPI REST endpoints
│   ├── metrics.py       # Prometheus metrics collector
│   ├── learning.py      # Bayesian calibration engine
│   └── streamer.py      # WebSocket telemetry broadcaster
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── openapi_spec.json
└── README.md
```

---

## 📄 License

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.
