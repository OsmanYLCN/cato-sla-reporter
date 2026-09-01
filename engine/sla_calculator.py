import pandas as pd
from datetime import timedelta

from config.settings import (
    PERIOD_LABELS,
    PERIOD_MINUTES,
    SLA_STATUS_FAILED,
    SLA_STATUS_PASSED,
    SLA_THRESHOLD_PCT,
)
from engine.state_machine import OutageRecord
from utils.logger import get_logger

logger = get_logger(__name__)

# Output DataFrame column names (English)
COL_OUT_SITE     = "Site Name"
COL_OUT_PERIOD   = "Report Period"
COL_OUT_COUNT    = "Outage Count"
COL_OUT_DURATION = "Total Downtime (Minutes)"
COL_OUT_AVAIL    = "Availability (%)"
COL_OUT_SLA      = "SLA Status"


def _merge_site_intervals(records: list[OutageRecord]) -> list[tuple]:
    """Merges overlapping outage intervals for the same site."""
    intervals = sorted((r.start, r.end) for r in records)
    merged: list[list] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]


def calculate_sla(
    outages: list[OutageRecord],
    all_sites: list[str],
    period_months: int,
    total_minutes: float | None = None,
) -> pd.DataFrame:
    """Calculates site-level availability (%) and SLA status from outage records."""
    if period_months not in PERIOD_MINUTES:
        raise ValueError(
            f"Geçersiz rapor dönemi: {period_months}. "
            f"Geçerli değerler: {list(PERIOD_MINUTES.keys())}"
        )

    calc_total_minutes = total_minutes if total_minutes is not None else float(PERIOD_MINUTES[period_months])
    period_label = PERIOD_LABELS[period_months]

    logger.info(
        "Starting SLA calculation. Period: %s | Total mins: %.2f | Threshold: %.2f%%",
        period_label, calc_total_minutes, SLA_THRESHOLD_PCT,
    )

    # Kesintileri grupla, çakışan aralıkları birleştir, süreyi hesapla
    site_outages: dict[str, list[OutageRecord]] = {}
    for record in outages:
        site_outages.setdefault(record.site, []).append(record)

    site_stats: dict[str, dict] = {}
    for site, records in site_outages.items():
        merged = _merge_site_intervals(records)
        total_td = sum((e - s for s, e in merged), timedelta())
        site_stats[site] = {
            "count": len(records),
            "total_minutes": total_td.total_seconds() / 60.0,
        }

    # Her site için Availability hesaplama
    rows: list[dict] = []

    for site in sorted(all_sites):
        stats = site_stats.get(site, {"count": 0, "total_minutes": 0.0})
        downtime_min: float = min(stats["total_minutes"], calc_total_minutes)

        availability = (
            ((calc_total_minutes - downtime_min) / calc_total_minutes) * 100
            if calc_total_minutes > 0
            else 100.0
        )
        sla_status = SLA_STATUS_PASSED if availability >= SLA_THRESHOLD_PCT else SLA_STATUS_FAILED

        rows.append({
            COL_OUT_SITE:     site,
            COL_OUT_PERIOD:   period_label,
            COL_OUT_COUNT:    stats["count"],
            COL_OUT_DURATION: round(downtime_min, 2),
            COL_OUT_AVAIL:    round(availability, 4),
            COL_OUT_SLA:      sla_status,
        })

        logger.debug(
            "%-30s | Outages: %2d | Downtime: %8.2f mins | Avail: %9.4f%% | %s",
            site,
            stats["count"],
            downtime_min,
            availability,
            sla_status,
        )

    summary_df = pd.DataFrame(rows)

    if not summary_df.empty:
        passed = (summary_df[COL_OUT_SLA] == SLA_STATUS_PASSED).sum()
        failed = (summary_df[COL_OUT_SLA] == SLA_STATUS_FAILED).sum()
        logger.info(
            "SLA calculation completed. Total sites: %d | Passed: %d | Failed: %d",
            len(summary_df), passed, failed,
        )
    else:
        logger.warning("No sites to calculate; returning empty DataFrame.")

    return summary_df

