# Options Swing Signal Pipeline

A simple Python pipeline to identify swing trading signals from options positioning across sector ETFs.

## Overview

This project:
- selects sector ETFs
- fetches holdings dynamically
- retrieves options chains for each holding
- filters unusual activity by volume/OI and DTE
- detects directional bias and strike clustering
- saves candidate signals for day-0 output
- confirms positions next trading day using open interest retention

## Setup

1. Create a virtual environment:

```bash
python -m venv .venv
.\.venv\Scripts\activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the pipeline:

```bash
python scripts/run_pipeline.py
```

## Files

- `src/options_signal_pipeline/pipeline.py`: core pipeline implementation
- `scripts/run_pipeline.py`: example script to execute the workflow
- `tests/test_pipeline.py`: unit test scaffold

## Notes

- Uses `yfinance` for ETF and options data
- Designed for end-of-day batch analysis, not intraday trading
- Built with modular functions for extendability
