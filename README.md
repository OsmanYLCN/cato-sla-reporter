# Cato Networks SLA & Availability Reporter System

A modular Python tool to calculate monthly and quarterly SLA/Availability metrics for sites connected to Cato Network Systems. 

For sites with multiple WAN links or HA configurations, the tool verifies if all interfaces are down simultaneously before recording a true outage, applying a time-window tolerance to filter out transient connection flaps.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### 1. Manual Mode
Calculates SLA for a rolling period (last 30 or 90 days) from today.

```bash
# Last 30 days
python main.py --input sample_data/Cato_events_sample.csv --period 1

# Last 90 days
python main.py --input sample_data/Cato_events_sample.csv --period 3
```

### 2. Auto Mode (for Cron / Schedulers)
Calculates SLA for the previous full calendar month or quarter.

```bash
# Previous calendar month
python main.py --input /path/to/events.csv --period 1 --mode auto
```

### Parameters

| Argument | Required | Default | Description |
|---|---|---|---|
| `--input` | Yes | None | Path to the event log CSV file. |
| `--period` | Yes | None | `1` (for 1 Month) or `3` (for 3 Months). |
| `--mode` | No | `manual` | `manual` (rolling days) or `auto` (previous calendar month/quarter). |
| `--output` | No | `./output` | Destination folder for the Excel report. |

## Core Logic & Business Rules

* **Timezone Conversion**: Timestamps in the CSV (UTC) are converted to `Europe/Istanbul` (UTC+3) before processing.
* **Outage Detection**: 
  * A site is only considered DOWN if all its interfaces (dynamically detected from the data) are down at the same time.
  * **Tolerance (30 seconds)**: If all interfaces disconnect, but any interface reconnects within 30 seconds, it is ignored as a transient flap.
  * **Net Downtime**: Calculated as the duration between the initial disconnect (after tolerance passes) and the first interface recovery.
  * **Open Outages**: Outages still active at the end of the reporting period are calculated up to the period end boundary.
* **Availability Formula**:
  $$\text{Availability} = \frac{\text{Total Period Minutes} - \text{Total Downtime}}{\text{Total Period Minutes}} \times 100$$
  * **Target SLA**: `99.90%`. Sites with availability below this are marked as `Failed`; otherwise `Passed`.
  * **Total Period Minutes**: Fixed at `43200` (1 Month) and `129600` (3 Months).

## Outputs

The tool generates `output/SLA_Report_<Period>M_<Date>_<Time>.xlsx` (e.g. `SLA_Report_1M_2026-08-31_14-30-00.xlsx`) containing:
1. **SLA Summary**: Site metrics (Downtime, Availability %, and SLA Status highlighted in green/red).
2. **Outage Details**: Granular audit log showing start/end timestamps and duration of each outage.

## Tests

To run unit tests:
```bash
pytest tests/ -v
```
