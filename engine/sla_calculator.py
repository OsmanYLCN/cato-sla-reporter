"""
engine/sla_calculator.py
=========================
Kesinti listesinden SLA özet tablosu üreten hesaplayıcı modül.

Sorumluluklar:
    - Site bazında kesintileri toplamak
    - Toplam kesinti süresini (dakika) hesaplamak
    - Availability (%) formülünü uygulamak
    - SLA Passed / Failed kararını vermek
    - Dönemde hiç kesintisi olmayan siteleri %100 / Passed olarak eklemek
    - Sonuç pd.DataFrame döndürmek
"""

import pandas as pd

from config.settings import (
    PERIOD_LABELS,
    PERIOD_MINUTES,
    SLA_THRESHOLD_PCT,
)
from engine.state_machine import OutageRecord
from utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Çıktı DataFrame Sütun İsimleri (sabit referans)
# ---------------------------------------------------------------------------
COL_OUT_SITE = "Site Name"
COL_OUT_PERIOD = "Rapor Dönemi"
COL_OUT_COUNT = "Gerçek Kesinti Sayısı"
COL_OUT_DURATION = "Toplam Kesinti Süresi (Dakika)"
COL_OUT_AVAIL = "Availability (%)"
COL_OUT_SLA = "SLA Durumu"


def calculate_sla(
    outages: list[OutageRecord],
    all_sites: list[str],
    period_months: int,
) -> pd.DataFrame:
    """
    Kesinti listesi ve tüm site listesinden SLA özet DataFrame'i üretir.

    Formül:
        Availability (%) = ((PERIOD_MINUTES - total_downtime_min) / PERIOD_MINUTES) * 100

    SLA Durumu:
        Availability >= SLA_THRESHOLD_PCT → "Passed"
        Availability <  SLA_THRESHOLD_PCT → "Failed"

    Logsuz siteler (all_sites içinde olup outages'ta olmayan):
        Hiç kesintisi yokmuş gibi → %100 / Passed olarak eklenir.

    Args:
        outages: state_machine.detect_outages() çıktısı.
        all_sites: Raporda yer alması gereken tüm site adları listesi.
        period_months: Rapor dönemi (1 veya 3).

    Returns:
        Özet SLA pd.DataFrame (6 sütun, 2 ondalıklı süre, 4 ondalıklı Availability).

    Raises:
        ValueError: Geçersiz period_months değeri verilirse.
    """
    if period_months not in PERIOD_MINUTES:
        raise ValueError(
            f"Geçersiz rapor dönemi: {period_months}. "
            f"Geçerli değerler: {list(PERIOD_MINUTES.keys())}"
        )

    total_minutes = PERIOD_MINUTES[period_months]
    period_label = PERIOD_LABELS[period_months]

    logger.info(
        "SLA hesabı başlıyor. Dönem: %s | Toplam dk: %d | Eşik: %%%s",
        period_label, total_minutes, SLA_THRESHOLD_PCT,
    )

    # -----------------------------------------------------------------------
    # Kesintileri site bazında topla
    # -----------------------------------------------------------------------
    site_stats: dict[str, dict] = {}

    for record in outages:
        if record.site not in site_stats:
            site_stats[record.site] = {"count": 0, "total_minutes": 0.0}
        site_stats[record.site]["count"] += 1
        site_stats[record.site]["total_minutes"] += record.duration_minutes

    # -----------------------------------------------------------------------
    # Tüm siteleri işle (logsuz siteler dahil)
    # -----------------------------------------------------------------------
    rows: list[dict] = []

    for site in sorted(all_sites):
        stats = site_stats.get(site, {"count": 0, "total_minutes": 0.0})
        downtime_min: float = min(stats["total_minutes"], total_minutes)  # aşım koruması

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

    # -----------------------------------------------------------------------
    # Özet loglama
    # -----------------------------------------------------------------------
    if not summary_df.empty:
        passed = (summary_df[COL_OUT_SLA] == "Passed").sum()
        failed = (summary_df[COL_OUT_SLA] == "Failed").sum()
        logger.info(
            "SLA hesabı tamamlandı. Toplam site: %d | Passed: %d | Failed: %d",
            len(summary_df), passed, failed,
        )
    else:
        logger.warning("Hesaplanacak site bulunamadı; boş DataFrame döndürülüyor.")

    return summary_df
