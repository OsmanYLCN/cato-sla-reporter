import pandas as pd
from datetime import timedelta

from config.settings import (
    PERIOD_LABELS,
    PERIOD_MINUTES,
    SLA_THRESHOLD_PCT,
)
from engine.state_machine import OutageRecord
from utils.logger import get_logger

logger = get_logger(__name__)

# Çıktı DataFrame sütun isimleri
COL_OUT_SITE = "Site Name"
COL_OUT_PERIOD = "Rapor Dönemi"
COL_OUT_COUNT = "Gerçek Kesinti Sayısı"
COL_OUT_DURATION = "Toplam Kesinti Süresi (Dakika)"
COL_OUT_AVAIL = "Availability (%)"
COL_OUT_SLA = "SLA Durumu"

# Site aralıklarını birleştirme
def _merge_site_intervals(records: list[OutageRecord]) -> list[tuple]:
    """Ayni site icin cakisan kesinti araliklerini birlestirir."""
    intervals = sorted((r.start, r.end) for r in records)
    merged: list[list] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]

# SLA hesaplama
def calculate_sla(
    outages: list[OutageRecord],
    all_sites: list[str],
    period_months: int,
) -> pd.DataFrame:
    """Kesinti kayitlarindan site bazli erisilebilirlik (%) ve SLA durumunu hesaplar."""
    if period_months not in PERIOD_MINUTES:
        raise ValueError(
            f"Geçersiz rapor dönemi: {period_months}. "
            f"Geçerli değerler: {list(PERIOD_MINUTES.keys())}"
        )

    total_minutes = PERIOD_MINUTES[period_months]
    period_label = PERIOD_LABELS[period_months]

    logger.info(
        "SLA hesabi basliyor. Dönem: %s | Toplam dk: %d | Eşik: %%%s",
        period_label, total_minutes, SLA_THRESHOLD_PCT,
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
        downtime_min: float = min(stats["total_minutes"], total_minutes)

        availability = ((total_minutes - downtime_min) / total_minutes) * 100
        sla_status = "Passed" if availability >= SLA_THRESHOLD_PCT else "Failed"

        rows.append({
            COL_OUT_SITE:     site,
            COL_OUT_PERIOD:   period_label,
            COL_OUT_COUNT:    stats["count"],
            COL_OUT_DURATION: round(downtime_min, 2),
            COL_OUT_AVAIL:    round(availability, 4),
            COL_OUT_SLA:      sla_status,
        })

        logger.debug(
            "%-30s | Kesinti: %2d | Downtime: %8.2f dk | Avail: %9.4f%% | %s",
            site,
            stats["count"],
            downtime_min,
            availability,
            sla_status,
        )

    summary_df = pd.DataFrame(rows)

    if not summary_df.empty:
        passed = (summary_df[COL_OUT_SLA] == "Passed").sum()
        failed = (summary_df[COL_OUT_SLA] == "Failed").sum()
        logger.info(
            "SLA hesabi tamamlandi. Toplam site: %d | Passed: %d | Failed: %d",
            len(summary_df), passed, failed,
        )
    else:
        logger.warning("Hesaplanacak site bulunamadi; bos DataFrame donduruluyor.")

    return summary_df
