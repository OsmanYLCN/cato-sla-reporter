# Cato Networks SLA & Availability Reporter System

A modular Python tool to calculate monthly and quarterly SLA/Availability metrics for sites connected to Cato Network Systems. 

For sites with multiple WAN links or HA configurations, the tool verifies if all interfaces are down simultaneously before recording a true outage, applying a time-window tolerance to filter out transient connection flaps.

## Installation & Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure environment variables (required for API mode):
   ```bash
   cp .env.example .env
   ```
   Provide your Cato credentials in `.env`:
   ```env
   CATO_ACCOUNT_ID=your_account_id_here
   CATO_API_KEY=your_api_key_here
   CATO_API_ENDPOINT=https://api.catonetworks.com/api/v1/graphql2
   ```

## Usage

### 1. API Mode (Live Cato GraphQL Ingestion)
Fetches connectivity event logs directly from Cato Networks via GraphQL API.

```bash
# Last 30 days (rolling)
python main.py --source api --period 1

# Last 90 days (rolling)
python main.py --source api --period 3

# Specific calendar month / custom date range
python main.py --source api --date-from 2026-08-01 --date-to 2026-08-31
```

### 2. CSV Mode (Local File Ingestion)
Processes pre-exported Cato event CSV files (legacy mode).

```bash
# Last 30 days
python main.py --source csv --input sample_data/Cato_events_sample.csv --period 1

# Previous full calendar month (for Cron / Schedulers)
python main.py --source csv --input sample_data/Cato_events_sample.csv --period 1 --mode auto
```

### CLI Parameters

| Argument | Required | Default | Description |
|---|---|---|---|
| `--source` | No | `csv` | Ingestion mode: `api` (direct Cato GraphQL) or `csv` (file import). |
| `--input` | Conditional | None | Path to CSV log file. **Required** when `--source csv`. |
| `--period` | Conditional | None | Report period: `1` (1 Month) or `3` (3 Months). Required unless using custom dates. |
| `--date-from` | Optional | None | Start date for custom range (`YYYY-MM-DD`). Used with `--date-to`. |
| `--date-to` | Optional | None | End date for custom range (`YYYY-MM-DD`). Used with `--date-from`. |
| `--mode` | No | `manual` | `manual` (rolling days) or `auto` (completed calendar month/quarter). |
| `--output` | No | `./output` | Destination folder for the generated Excel report. |

## Core Logic & Business Rules

* **Timezone Normalization**: UTC timestamps (from API or CSV) are normalized to `Europe/Istanbul` (UTC+3).
* **Outage Detection**: 
  * A site is only flagged as DOWN if all its interfaces (dynamically detected) disconnect concurrently.
  * **Correlation Tolerance (30s)**: Transient disconnects lasting $\le 30$ seconds before any interface recovers are treated as flaps and discarded.
  * **Net Downtime**: Measured from initial drop to first interface recovery.
  * **Open Outages**: Active outages at period boundaries are capped at the period end timestamp.
* **Availability Formula**:
  $$\text{Availability} = \frac{\text{Total Period Minutes} - \text{Total Downtime}}{\text{Total Period Minutes}} \times 100$$
  * **Target SLA**: `99.90%`. Sites meeting or exceeding this are `Passed`, otherwise `Failed`.

## Outputs

Generated Excel reports are saved to `output/SLA_Report_<Period>_<Timestamp>.xlsx` containing 3 dedicated sheets:
1. **SLA Summary**: Site-by-site availability metrics, downtime minutes, and SLA compliance status (color-coded).
2. **Outage Details**: Comprehensive audit log recording start/end timestamps and duration for each outage event.
3. **Overall Summary**: Executive overview showing total site count, overall availability average, and SLA pass/fail rates.

## Tests

Run the test suite (74 unit tests covering API client, state machine, CLI, and calculators):
```bash
pytest tests/ -v
```
