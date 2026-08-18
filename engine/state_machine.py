from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd

from config.settings import (
    COL_EVENT,
    COL_IFACE,
    COL_ROLE,
    COL_SITE,
    COL_TIME,
    CORRELATION_WINDOW_SECONDS,
)
from engine.leg_detector import LegMap
from utils.logger import get_logger

logger = get_logger(__name__)

# Kesinti kaydı ve durum makinesi sınıfları
@dataclass
class OutageRecord:
    """Tekil bir site kesinti kaydi."""
    site: str
    start: datetime
    end: datetime

    @property
    def duration_minutes(self) -> float:
        """Kesinti süresini dakika cinsinden hesaplar."""
        delta = self.end - self.start
        return round(delta.total_seconds() / 60.0, 2)

# Site durum makinesi sınıfı
@dataclass
class _SiteState:
    """Durum makinesi icin anlik site durum verisi."""
    leg_status: dict[tuple[str, str], str] = field(default_factory=dict)
    state: str = "UP"
    candidate_since: datetime | None = None
    down_since: datetime | None = None

    def all_disconnected(self) -> bool:
        if not self.leg_status:
            return False
        return all(s == "Disconnected" for s in self.leg_status.values())

    def any_connected(self) -> bool:
        return any(s == "Connected" for s in self.leg_status.values())

# Kesinti tespiti
def detect_outages(
    df: pd.DataFrame,
    leg_map: LegMap,
    period_start: datetime,
    period_end: datetime,
) -> list[OutageRecord]:
    """Zaman pencereli durum makinesi kullanarak gercek site kesintilerini tespit eder."""
    logger.info(
        "Kesinti tespiti basliyor. Dönem: %s → %s",
        period_start.strftime("%Y-%m-%d %H:%M:%S %Z"),
        period_end.strftime("%Y-%m-%d %H:%M:%S %Z"),
    )

    tolerance = timedelta(seconds=CORRELATION_WINDOW_SECONDS)
    outages: list[OutageRecord] = []
    leg_map = dict(leg_map)  

    mask = (df[COL_TIME] >= period_start) & (df[COL_TIME] <= period_end)
    df_period = df[mask].copy()

    if df_period.empty:
        logger.warning(
            "Rapor döneminde (%s → %s) hic log kaydi bulunamadi.",
            period_start, period_end,
        )
        return outages

    # Site durumlarını varsayılan olarak UP ile başlat
    site_states: dict[str, _SiteState] = {}
    for site, legs in leg_map.items():
        state = _SiteState()
        for leg in legs:
            state.leg_status[leg] = "Connected"
        site_states[site] = state

    logger.debug("%d site icin durum makinesi baslatildi.", len(site_states))

    # Olayları kronolojik sırayla işleyerek durum geçişlerini hesaplama
    for row in df_period.itertuples(index=False):
        site: str = getattr(row, COL_SITE)
        event_time: datetime = getattr(row, COL_TIME)
        event_type: str = getattr(row, COL_EVENT)
        leg_key: tuple[str, str] = (getattr(row, COL_IFACE), getattr(row, COL_ROLE))

        if site not in site_states:
            logger.debug(
                "Bacak haritasinda olmayan site bulundu, ekleniyor: '%s'", site
            )
            state = _SiteState()
            state.leg_status[leg_key] = event_type
            site_states[site] = state
            leg_map[site] = frozenset({leg_key})
            continue

        state = site_states[site]
        state.leg_status[leg_key] = event_type

        _process_event(
            site=site,
            state=state,
            event_time=event_time,
            tolerance=tolerance,
            outages=outages,
            period_end=period_end,
        )

    # Dönem sonunda açık kalan kesintileri kapatma
    for site, state in site_states.items():
        if state.state == "DOWN" and state.down_since is not None:
            rec = OutageRecord(
                site=site,
                start=state.down_since,
                end=period_end,
            )
            outages.append(rec)
            logger.debug(
                "[%s] Donem sonunda acik kesinti kapatildi. "
                "Baslangic: %s | Bitis (donem sonu): %s | Sure: %.2f dk",
                site,
                state.down_since,
                period_end,
                rec.duration_minutes,
            )
        elif state.state == "CANDIDATE" and state.candidate_since is not None:
            rec = OutageRecord(
                site=site,
                start=state.candidate_since,
                end=period_end,
            )
            outages.append(rec)
            logger.debug(
                "[%s] CANDIDATE durumunda dönem bitti; DOWN olarak kaydedildi. "
                "Sure: %.2f dk",
                site,
                rec.duration_minutes,
            )

    logger.info(
        "Kesinti tespiti tamamlandi. Toplam gercek kesinti: %d", len(outages)
    )
    return outages

# Olay bazlı durum geçişlerini yöneten yardımcı fonksiyon
def _process_event(
    site: str,
    state: _SiteState,
    event_time: datetime,
    tolerance: timedelta,
    outages: list[OutageRecord],
    period_end: datetime,
) -> None:
    """Olay bazli durum gecislerini yonetir (UP -> CANDIDATE -> DOWN -> UP)."""
    current_state = state.state

    if current_state == "UP":
        if state.all_disconnected():
            state.state = "CANDIDATE"
            state.candidate_since = event_time
            logger.debug(
                "[%s] UP → CANDIDATE. Tum bacaklar Disconnected @ %s. "
                "Tolerans penceresi: %ds.",
                site, event_time, CORRELATION_WINDOW_SECONDS,
            )

    elif current_state == "CANDIDATE":
        if state.candidate_since is None:
            raise RuntimeError(
                f"[{site}] CANDIDATE durumunda candidate_since None olamaz."
            )
        elapsed = event_time - state.candidate_since

        if state.any_connected():
            if elapsed <= tolerance:
                # Tolerans süresi içindeki kısa kopmaları dalgalanma (flap) kabul edip yok say
                logger.debug(
                    "[%s] CANDIDATE → UP. Bacak Connected geldi (pencere ici, %.1fs), "
                    "tolerans devreye girdi @ %s.",
                    site, elapsed.total_seconds(), event_time,
                )
                state.state = "UP"
                state.candidate_since = None
            else:
                # Tolerans süresini aşan kesinti bağlandığında kapatılır
                rec = OutageRecord(
                    site=site,
                    start=state.candidate_since,
                    end=event_time,
                )
                outages.append(rec)
                logger.debug(
                    "[%s] CANDIDATE → UP (gec toparlanma). "
                    "Gercek kesinti: %s → %s (%.2f dk)",
                    site, state.candidate_since, event_time, rec.duration_minutes,
                )
                state.state = "UP"
                state.candidate_since = None

        elif state.all_disconnected():
            if elapsed >= tolerance:
                # Tolerans süresi dolduğunda site gerçek DOWN durumuna geçer
                state.state = "DOWN"
                state.down_since = state.candidate_since
                state.candidate_since = None
                logger.debug(
                    "[%s] CANDIDATE → DOWN. Tolerans asildi (%.1fs). "
                    "Gercek kesinti baslangici: %s",
                    site, elapsed.total_seconds(), state.down_since,
                )

    elif current_state == "DOWN":
        if state.any_connected():
            # En az bir bacak bağlandığında kesintiyi sonlandır
            if state.down_since is not None:
                rec = OutageRecord(
                    site=site,
                    start=state.down_since,
                    end=event_time,
                )
                outages.append(rec)
                logger.debug(
                    "[%s] DOWN → UP. Kesinti bitti @ %s. Süre: %.2f dk",
                    site, event_time, rec.duration_minutes,
                )

            state.state = "UP"
            state.down_since = None
