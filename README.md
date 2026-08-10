# Cato Networks SLA and Availability Reporter

An enterprise-grade, modular Python application designed to parse Cato Networks device event logs, correlate multi-WAN/HA connectivity states, and generate location-based Monthly and Quarterly Service Level Agreement (SLA) / Availability reports.

---

## Architecture Overview

The codebase is structured under strict Separation of Concerns (SoC) principles to allow independent scalability, unit testing, and future integrations (such as API ingestion or SMTP delivery).

```
cato-sla-reporter/
├── main.py                    # CLI execution entry point and orchestrator
├── config/settings.py         # Centralized configuration and thresholds
├── data_ingestion/
│   ├── base_reader.py         # Abstract base class for data ingestion interfaces
│   ├── csv_reader.py          # CSV parser implementing BaseLogReader
│   └── graphql_reader.py      # Stub implementation for future GraphQL API integration
├── preprocessing/
│   └── transformer.py         # UTC parsing, timezone localization, and sanitization
├── engine/
│   ├── leg_detector.py        # Dynamic network interface and role discovery
│   ├── state_machine.py       # Time-windowed outage correlation engine
│   └── sla_calculator.py      # SLA metrics and availability calculation
├── reporting/
│   ├── excel_exporter.py      # Formatted multi-sheet Excel generation
│   └── email_sender.py        # Stub implementation for future SMTP notification
├── utils/logger.py            # Central logging mechanism
├── tests/                     # Unit test suites (pytest)
├── sample_data/               # Directory for raw log files
└── output/                    # Target directory for generated Excel reports
```

---

## Getting Started

### Prerequisites
- Python 3.9 or higher
- Windows/Linux/macOS environment

### Installation
Install the required dependencies using pip:
```bash
pip install -r requirements.txt
```

---

## Execution and Usage

### 1. Manual Execution Mode
Designed for local execution and ad-hoc analysis. The period flags target a rolling window of the last 30 or 90 days.

```bash
# Analyze rolling 30-day period (Last 1 Month)
python main.py --input sample_data/Cato_events_sample.csv --period 1

# Analyze rolling 90-day period (Last 3 Months) with custom output destination
python main.py --input sample_data/Cato_events_sample.csv --period 3 --output ./custom_reports
```

### 2. Automated Execution Mode
Designed for server execution via cron jobs or automated schedulers. The period flags target the previous full calendar month or quarter.

```bash
# Analyze the previous calendar month
python main.py --input /var/log/cato_events.csv --period 1 --mode auto
```

### Parameter Reference

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `--input` | String | Yes | None | Absolute or relative path to the raw log CSV file. |
| `--period` | Integer | Yes | None | Analysis timeframe. Allowed values: `1` (1 Month) or `3` (3 Months). |
| `--mode` | String | No | `manual` | Execution mode. Allowed values: `manual` (rolling days) or `auto` (calendar periods). |
| `--output` | String | No | `./output` | Destination directory for the generated Excel file. |

---

## Core Algorithms and Business Logic

### Timezone Conversion
Raw logs are assumed to contain timestamps in UTC (+0). The preprocessor converts these to the local operating timezone (`Europe/Istanbul`, UTC+3) to ensure reporting aligns with local business hours.

### Outage Correlation Engine
For locations utilizing dual-ISP (e.g., WAN1 and WAN2) or High Availability (HA) configurations, the disconnection of a single interface does not constitute an operational outage. The engine applies the following logic:
1. **Dynamic Interface Mapping**: Discovers all active interface and role pairs `(socket_interface, socket_role)` for each site dynamically from the log history.
2. **Correlation Window (Tolerance)**: Mitigates short-lived state flips. When all interfaces at a site disconnect, a 30-second window is monitored. If any interface reconnects within 30 seconds, no outage is recorded.
3. **Net Outage Duration**: Calculated as the delta between the time all interfaces are confirmed disconnected (beyond the tolerance threshold) and the time the first interface returns to a `Connected` state.
4. **Open Outages**: If a site is disconnected at the boundary of the reporting window, the outage duration is calculated up to the end of the reporting period.

### Metric Formula
- **SLA Efficacy Formula**: 
  $$\text{Availability (\%)} = \frac{\text{Total Period Minutes} - \text{Total Net Outage Minutes}}{\text{Total Period Minutes}} \times 100$$
- **Threshold**: The SLA target is set to `99.90%`. Sites falling below this threshold are flagged as `Failed`, while sites at or above the threshold are marked as `Passed`.
- **Period Minutes Constants**: Fixed at `43,200` minutes for 1 Month, and `129,600` minutes for 3 Months.

---

## Output Generation

The program outputs an Excel spreadsheet named `SLA_Report_<Period>M_<YYYY-MM-DD>.xlsx` containing two sheets:

1. **SLA Özet (Summary)**: 
   - Tabulates Site Name, Report Period, Outage Count, Total Outage Minutes (2 decimal places), Availability (4 decimal places), and SLA Status.
   - Highlights SLA Status cell backgrounds programmatically: `Passed` in green, `Failed` in red.
2. **Kesinti Detayları (Outage Details)**:
   - Provides granular logs containing Site Name, Start Time, End Time, and Duration in minutes for audit purposes.

---

## Automated Verification

Run the test suite using pytest to verify module transformations, state transitions, and SLA calculation logic:

```bash
pytest tests/ -v
```
