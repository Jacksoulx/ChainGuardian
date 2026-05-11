# ChainGuardian: A Blockchain Security Monitoring Prototype with Machine Learning and LLM-Assisted Interpretation

ChainGuardian is a local capstone prototype for blockchain consensus-security monitoring, anomaly detection, and LLM-assisted interpretation. The repository contains a Python backend for telemetry collection and detector workflows, plus a React dashboard interface for visualizing metrics, anomalies, artifacts, and terminal-style interactions.

The Python source tree currently lives under `aiagent/` because of the repository layout. That folder name is an internal implementation detail, not the project brand.

## Project Identity

- Overall project: `ChainGuardian`
- Python backend / CLI prototype: ChainGuardian research workflows
- Frontend / dashboard interface: ChainGuardian dashboard
- Internal Python source tree: `aiagent/`

## Project Overview

The current codebase implements a working prototype that can:

- collect recent Ethereum canonical blocks through JSON-RPC
- derive detector-compatible consensus metrics
- score metrics with rule-based logic and Isolation Forest
- generate dry-run or LLM-assisted Markdown reports
- save JSON, CSV, and Markdown artifacts for later inspection
- present a dark-themed analyst dashboard with metric cards, charts, a table of artifacts, and a PowerShell-style terminal mockup

The backend is implemented in Python. The dashboard is implemented in React with Tailwind CSS, Recharts, and lucide-react.

## Motivation

The project exists to explore how blockchain security monitoring can be made more practical and analyst-friendly. The motivating ideas are:

- consensus-layer attacks are security-critical because they affect ledger integrity
- the classical 51% attack remains a useful threat model for PoW systems
- Ethereum post-Merge requires PoS-aware interpretation rather than literal PoW hashrate reasoning
- real attack labels are rare, so anomaly detection is useful as a first-pass monitoring tool
- analysts need readable explanations, not only raw detector output

The codebase therefore combines telemetry collection, anomaly detection, and interpretability rather than focusing on a single classifier.

## Key Features

- Python CLI with two modes:
  - simple chat mode
  - research mode with blockchain security workflows
- Mock chain analysis for demo and regression coverage
- Statistical baseline training on generated mock samples
- CSV-based Isolation Forest workflow
- Ethereum JSON-RPC telemetry collection
- Canonical block parsing and feature extraction
- Rolling-window Ethereum metrics export to CSV
- Rule-based anomaly scoring
- Isolation Forest anomaly scoring
- Dry-run Markdown reporting without LLM output
- LLM-assisted interpretation for research workflows
- React/Tailwind dashboard branded as ChainGuardian
- Recharts line chart with anomaly markers
- Mock PowerShell-style terminal with command echoes and auto-scroll behavior
- Pytest coverage for parsing, telemetry, detection, retries, and artifact generation

## System Architecture

```text
           +------------------------------+
           |        ChainGuardian         |
           |  Python backend / CLI        |
           |                              |
           |  - mock chain metrics        |
           |  - Ethereum JSON-RPC client  |
           |  - metric builder            |
           |  - rule-based detector       |
           |  - statistical baseline      |
           |  - Isolation Forest          |
           |  - LLM interpretation        |
           |  - artifact writer           |
           +--------------+---------------+
                          |
                          | JSON / CSV / Markdown artifacts
                          v
           +------------------------------+
           |        ChainGuardian         |
           | React dashboard interface    |
           |                              |
           |  - metric cards              |
           |  - anomaly chart             |
           |  - artifact table            |
           |  - terminal mockup           |
           +------------------------------+
```

Data flow:

1. The backend fetches or generates telemetry.
2. The metric builder converts raw data into the shared detector schema.
3. The detectors produce anomaly scores, flags, and summaries.
4. The research agent writes JSON, CSV, and Markdown artifacts.
5. The dashboard presents the results in an analyst-facing interface.

Important note: the current ChainGuardian frontend uses simulated live data and predefined command responses. It mirrors the backend workflow, but it is not yet connected to a live backend API.

## Repository Structure

```text
.
├── main.py
├── README.md
├── requirements.txt
├── aiagent/
│   ├── cli.py
│   ├── agents/
│   │   ├── chat_agent.py
│   │   └── research_agent.py
│   ├── blockchain/
│   │   ├── ethereum_client.py
│   │   ├── metrics_builder.py
│   │   ├── mock_chain.py
│   │   ├── rpc_client.py
│   │   └── schemas.py
│   └── detectors/
│       ├── csv_loader.py
│       ├── evaluation.py
│       ├── isolation_forest_detector.py
│       ├── simple_anomaly.py
│       ├── training.py
│       └── schemas.py
├── dashboard/
│   ├── package.json
│   ├── src/
│   │   ├── App.jsx
│   │   ├── index.css
│   │   └── main.jsx
│   └── tailwind.config.js
├── data/
│   └── mock_metrics.csv
├── tests/
│   ├── test_ethereum_pipeline.py
│   └── test_mock_regression.py
```

## Installation

### 1. Python backend

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Frontend dashboard

```powershell
cd dashboard
npm install
```

## Configuration

Set the required environment variables in the same PowerShell session before running the relevant commands:

```powershell
$env:ETH_RPC_URL = "https://eth-mainnet.g.alchemy.com/v2/<YOUR_ALCHEMY_KEY>"
$env:OPENAI_API_KEY = "<YOUR_OPENAI_API_KEY>"
```

Notes:

- `ETH_RPC_URL` is required for real Ethereum JSON-RPC telemetry commands.
- `OPENAI_API_KEY` is required for the LLM-backed research workflows.
- Dry-run Ethereum analysis still needs `ETH_RPC_URL`, but it does not need the OpenAI key.
- The codebase treats `hashrate_concentration_top1`, `hashrate_concentration_top3`, and `miner_entropy` as legacy or proxy fields when applied to Ethereum post-Merge.

## Usage

### Backend CLI

```powershell
python main.py
python main.py research
```

### Research workflows

```text
analyze mock chain
train mock detector
analyze csv detector
analyze csv detector data/mock_metrics.csv
analyze eth chain dryrun 100
analyze eth chain --no-llm 100
collect eth metrics 500 data/eth_metrics_latest.csv
analyze eth detector
analyze real chain
analyze eth chain 100
```

Recommended local demo flow:

```powershell
python main.py research
```

Then run:

```text
analyze eth chain dryrun 100
collect eth metrics 500 data/eth_metrics_latest.csv
analyze eth detector
```

### Frontend dashboard

```powershell
cd dashboard
npm run dev
```

Build the dashboard:

```powershell
cd dashboard
npm run build
```

Preview the production build:

```powershell
cd dashboard
npm run preview
```

## Testing

Run the Python test suite from the repository root after activating your virtual environment:

```powershell
python -m pytest
```

Optional syntax check:

```powershell
python -m compileall aiagent
```

## Current Status

The project is a functional local prototype and capstone demonstration.

It currently provides:

- a Python research CLI
- Ethereum telemetry and detector workflows
- a dark-themed dashboard UI
- artifact generation for reports and analysis
- regression tests for core backend behavior

It is not yet a production monitoring platform, and the frontend is not yet wired to a live backend API.

## Limitations

- Canonical Ethereum JSON-RPC does not expose the full consensus picture.
- `fork_rate`, `orphan_rate`, and `reorg_depth_max` are placeholders for Ethereum RPC-only telemetry.
- `hashrate_*` feature names are legacy schema names and should be read as proposer / fee-recipient concentration proxies on Ethereum.
- The mock CSV dataset is small and intended for demonstration.
- There is no large-scale quantitative benchmark in the repository yet.
- LLM-generated explanations are advisory and should not be treated as authoritative security conclusions.

## Future Work

- collect longer real Ethereum telemetry windows
- add richer PoS-aware metrics from beacon-chain and validator sources
- connect ChainGuardian to the backend through an API
- evaluate against labeled historical incidents or realistic simulations
- add broader chain support and stronger report automation
- add deployment, scheduling, and alerting support

## Local Report Artifacts

The capstone LaTeX report workspace is kept local under `final_report/` and is intentionally ignored by Git. It is not part of the GitHub repository contents.
