# Australia Economic Pulse Dashboard

A fully automated data pipeline that downloads, cleans, and visualises key Australian macroeconomic indicators — refreshed weekly via GitHub Actions and presented in a Power BI dashboard.

---

## Overview

Tracking Australia's economic health requires pulling data from multiple government sources that publish on different schedules and in different formats. This project solves that by:

1. Automatically fetching the latest datasets from the ABS and RBA every Monday
2. Standardising them into a single tidy CSV
3. Surfacing the data in an interactive Power BI dashboard for analysis and storytelling

The pipeline runs entirely in the cloud with no manual steps required after the initial setup.

---

## Data Sources

| Indicator | Source | Series | Frequency |
|---|---|---|---|
| Consumer Price Index (CPI) | Australian Bureau of Statistics | Cat. 6401.0 | Quarterly |
| Unemployment Rate | Australian Bureau of Statistics | Cat. 6202.0 | Monthly |
| Wage Price Index (WPI) | Australian Bureau of Statistics | Cat. 6345.0 | Quarterly |
| Gross Domestic Product (GDP) | Australian Bureau of Statistics | Cat. 5206.0 | Quarterly |
| Cash Rate Target | Reserve Bank of Australia | Table A2 | Monthly |

All datasets are sourced directly from official government portals and are free to use.

---

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     GitHub Actions (weekly)                     │
│                                                                 │
│   fetch_abs.py          fetch_rba.py         build_dataset.py  │
│   ─────────────         ──────────────       ────────────────  │
│   Downloads ABS   →     Downloads RBA   →    Cleans & merges   │
│   Excel files           Excel files          all indicators     │
│   → data/raw/           → data/raw/          → data/clean/     │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
                    data/clean/economic_indicators.csv
                                │
                                ▼
                    ┌───────────────────────┐
                    │  Power BI Dashboard   │
                    └───────────────────────┘
```

### Output Schema

The pipeline produces a single normalised file consumed by Power BI:

| Column | Type | Description |
|---|---|---|
| `date` | Date | End-of-month observation date |
| `indicator` | Text | Series name (e.g. "CPI All Groups") |
| `value` | Number | Observation value |
| `unit` | Text | Unit of measure (e.g. "Percent", "$ Million") |
| `frequency` | Text | "Monthly" or "Quarterly" |
| `source` | Text | "ABS" or "RBA" |

---

## Technologies Used

| Tool | Role |
|---|---|
| Python 3.12 | Data extraction and transformation |
| pandas | Data cleaning and reshaping |
| requests | HTTP downloads from ABS and RBA |
| openpyxl / xlrd | Parsing `.xlsx` and `.xls` Excel files |
| GitHub Actions | Scheduled weekly pipeline execution |
| Power BI | Interactive dashboard and visualisation |

---

## Repository Structure

```
aus-economic-pulse/
├── .github/
│   └── workflows/
│       └── update-data.yml      # Weekly GitHub Actions workflow
├── data/
│   ├── raw/                     # Downloaded source Excel files (auto-generated)
│   └── clean/
│       └── economic_indicators.csv   # Final dataset for Power BI
├── scripts/
│   ├── fetch_abs.py             # Downloads ABS datasets
│   ├── fetch_rba.py             # Downloads RBA datasets
│   └── build_dataset.py        # Cleans and merges all indicators
└── requirements.txt
```

---

## Dashboard Features

- **CPI trend** — quarterly inflation trajectory with year-on-year change
- **Unemployment rate** — monthly labour market conditions over time
- **Wage growth vs inflation** — dual-axis comparison of WPI against CPI
- **GDP growth** — quarterly chain volume measure with period-on-period growth
- **Cash rate timeline** — RBA monetary policy decisions over the economic cycle
- **Cross-indicator view** — overlay any combination of indicators for custom analysis
- **Date slicer** — filter all visuals to any custom date range

---

## Getting Started

### Prerequisites

- Python 3.12+
- Power BI Desktop (for viewing the dashboard locally)

### Run the pipeline locally

```bash
# Install dependencies
pip install -r requirements.txt

# Download raw data
python scripts/fetch_abs.py
python scripts/fetch_rba.py

# Build the clean dataset
python scripts/build_dataset.py
```

The output file will be written to `data/clean/economic_indicators.csv`.

### Automated updates

Push the repository to GitHub and the workflow in `.github/workflows/update-data.yml` will run automatically every Monday at 01:00 UTC. Updated data files are committed back to the repository automatically.

---

## Future Improvements

- Add additional indicators: housing approvals, retail trade, business confidence
- Publish `economic_indicators.csv` as a GitHub Pages static asset for direct Power BI web connector access
- Add data validation step to flag anomalous values before committing
- Send a Slack or email notification if a download fails
- Extend coverage to state-level economic data where available from ABS

---

## Data Licences

- ABS data is released under the [Creative Commons Attribution 4.0 International licence](https://www.abs.gov.au/website-privacy-copyright-and-disclaimer)
- RBA data is released under the [Creative Commons Attribution 4.0 International licence](https://www.rba.gov.au/copyright/)
