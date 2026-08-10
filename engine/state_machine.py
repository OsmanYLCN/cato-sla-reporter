"""
engine/state_machine.py
========================
Kesinti Korelasyon Motoru — Projenin en kritik modülü.

Zaman pencereli (time-windowed) bir Durum Makinesi (State Machine) ile
çok bacaklı sitelerde gerçek site kesintilerini tespit eder.

Algoritma Özeti:
    1. Her site için olaylar kronolojik sırayla işlenir.
    2. Her olayda ilgili bacağın durumu güncellenir.
    3. Tüm bacaklar "Disconnected" olduğu anda bir tolerans penceresi
       (CORRELATION_WINDOW_SECONDS) başlatılır.
    4. Pencere içinde herhangi bir bacak "Connected" olursa DOWN iptal edilir
       (bu bir geçici titreme/flap olarak değerlendirilir).
    5. Pencere kapandığında hâlâ tüm bacaklar DOWN ise "Gerçek DOWN" başlar.
    6. En az 1 bacak "Connected" olduğunda DOWN biter.
    7. Dönem sonunda hâlâ DOWN olan siteler, bitiş zamanı = dönem sonu olarak kaydedilir.

Durum Geçişleri:
    UP ─[tüm bacaklar Disconnected + pencere geçti]─► CANDIDATE ─[pencere kapandı]─► DOWN
    DOWN ─[en az 1 bacak Connected]─► UP
    CANDIDATE ─[en az 1 bacak Connected]─► UP  (tolerans devreye girdi)
"""

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


# ---------------------------------------------------------------------------
# Veri Yapıları
# ---------------------------------------------------------------------------

@dataclass
class OutageRecord:
    """Tek bir gerçek site kesintisini temsil eder."""
    site: str
    start: datetime
    end: datetime

    @property
    def duration_minutes(self) -> float:
        """Kesinti süresini dakika cinsinden döndürür (2 ondalık hassasiyet)."""
        delta = self.end - self.start
        return round(delta.total_seconds() / 60.0, 2)


@dataclass
class _SiteState:
    """Durum makinesi boyunca bir sitenin anlık durumunu tutar."""
    # Bacak adı → "Connected" | "Disconnected"
    leg_status: dict[tuple[str, str], str] = field(default_factory=dict)

    # Mevcut durum: "UP" | "CANDIDATE" | "DOWN"
    state: str = "UP"

    # CANDIDATE durumuna girildiği zaman (tolerans penceresi başlangıcı)
    candidate_since: datetime | None = None

    # DOWN durumuna girildiği zaman (gerçek kesinti başlangıcı)
    down_since: datetime | None = None

    def all_disconnected(self) -> bool:
        """Tüm bilinen bacaklar Disconnected ise True döndürür."""
        if not self.leg_status:
            return False
        return all(s == "Disconnected" for s in self.leg_status.values())

    def any_connected(self) -> bool:
        """En az 1 bacak Connected ise True döndürür."""
        return any(s == "Connected" for s in self.leg_status.values())


# ---------------------------------------------------------------------------
# Ana Fonksiyon
# ---------------------------------------------------------------------------

def detect_outages(
    df: pd.DataFrame,
    leg_map: LegMap,
    period_start: datetime,
    period_end: datetime,
) -> list[OutageRecord]:
    """
    Temizlenmiş log DataFrame'ini ve bacak haritasını kullanarak
    gerçek site kesintilerinin listesini üretir.

    Args:
        df: Transformer'dan geçirilmiş, timezone-aware log DataFrame'i.
        leg_map: `leg_detector.detect_legs()` çıktısı — site → bacak kümesi.
        period_start: Rapor döneminin başlangıç anı (timezone-aware).
        period_end: Rapor döneminin bitiş anı (timezone-aware).

    Returns:
        OutageRecord nesnelerinden oluşan liste.
        Her kayıt bir gerçek site kesintisini temsil eder.
    """
    logger.info(
        "Kesinti tespiti başlıyor. Dönem: %s → %s",
        period_start.strftime("%Y-%m-%d %H:%M:%S %Z"),
        period_end.strftime("%Y-%m-%d %H:%M:%S %Z"),
    )

    tolerance = timedelta(seconds=CORRELATION_WINDOW_SECONDS)
    outages: list[OutageRecord] = []

    # Rapor dönemindeki olayları filtrele
    mask = (df[COL_TIME] >= period_start) & (df[COL_TIME] <= period_end)
    df_period = df[mask].copy()

    if df_period.empty:
        logger.warning(
            "Rapor döneminde (%s → %s) hiç log kaydı bulunamadı.",
            period_start, period_end,
        )
        return outages

    # Her site için durum makinesi başlat
    site_states: dict[str, _SiteState] = {}
    for site, legs in leg_map.items():
        state = _SiteState()
        # Başlangıçta tüm bacakları "Connected" kabul et
        for leg in legs:
            state.leg_status[leg] = "Connected"
        site_states[site] = state

    logger.debug("%d site için durum makinesi başlatıldı.", len(site_states))

    # -----------------------------------------------------------------------
    # Olayları kronolojik sırayla işle
    # -----------------------------------------------------------------------
    for _, row in df_period.iterrows():
        site: str = row[COL_SITE]
        event_time: datetime = row[COL_TIME]
        event_type: str = row[COL_EVENT]
        leg_key: tuple[str, str] = (row[COL_IFACE], row[COL_ROLE])

        # Bilinmeyen site (bacak haritasında yoksa): dinamik ekle
        if site not in site_states:
            logger.debug(
                "Bacak haritasında olmayan site bulundu, ekleniyor: '%s'", site
            )
            state = _SiteState()
            state.leg_status[leg_key] = event_type
            site_states[site] = state
            # Bacak haritasını da güncelle
            leg_map[site] = frozenset({leg_key})
            continue

        state = site_states[site]

        # Bacak durumunu güncelle
        state.leg_status[leg_key] = event_type

        # -------------------------------------------------------------------
        # Durum Makinesi Geçişleri
        # -------------------------------------------------------------------
        _process_event(
            site=site,
            state=state,
            event_time=event_time,
            tolerance=tolerance,
            outages=outages,
            period_end=period_end,
        )

    # -----------------------------------------------------------------------
    # Dönem sonu: Hâlâ DOWN olan siteleri kapat
    # -----------------------------------------------------------------------
    for site, state in site_states.items():
        if state.state == "DOWN" and state.down_since is not None:
            rec = OutageRecord(
                site=site,
                start=state.down_since,
                end=period_end,
            )
            outages.append(rec)
            logger.debug(
                "[%s] Dönem sonunda açık kesinti kapatıldı. "
                "Başlangıç: %s | Bitiş (dönem sonu): %s | Süre: %.2f dk",
                site,
                state.down_since,
                period_end,
                rec.duration_minutes,
            )
        elif state.state == "CANDIDATE" and state.candidate_since is not None:
            # Tolerans penceresi kapanmadan dönem bitti: yine de DOWN say
            rec = OutageRecord(
                site=site,
                start=state.candidate_since,
                end=period_end,
            )
            outages.append(rec)
            logger.debug(
                "[%s] CANDIDATE durumunda dönem bitti; DOWN olarak kaydedildi. "
                "Süre: %.2f dk",
                site,
                rec.duration_minutes,
            )

    logger.info(
        "Kesinti tespiti tamamlandı. Toplam gerçek kesinti: %d", len(outages)
    )
    return outages


def _process_event(
    site: str,
    state: _SiteState,
    event_time: datetime,
    tolerance: timedelta,
    outages: list[OutageRecord],
    period_end: datetime,
) -> None:
    """
    Tek bir olayı mevcut site durumuna göre işler ve gerekirse durum geçişi yapar.

    Args:
        site: Site adı (loglama için).
        state: Sitenin mevcut _SiteState nesnesi (mutable, yerinde güncellenir).
        event_time: Olayın gerçekleştiği zaman.
        tolerance: Korelasyon tolerans süresi (timedelta).
        outages: Tamamlanan kesintilerin eklendiği liste (mutable).
        period_end: Rapor dönemi bitiş zamanı (dönem sonu kesintileri için).
    """
    current_state = state.state

    if current_state == "UP":
        # Tüm bacaklar down mı? → CANDIDATE'e geç
        if state.all_disconnected():
            state.state = "CANDIDATE"
            state.candidate_since = event_time
            logger.debug(
                "[%s] UP → CANDIDATE. Tüm bacaklar Disconnected @ %s. "
                "Tolerans penceresi: %ds.",
                site, event_time, CORRELATION_WINDOW_SECONDS,
            )

    elif current_state == "CANDIDATE":
        assert state.candidate_since is not None
        elapsed = event_time - state.candidate_since

        if state.any_connected():
            if elapsed <= tolerance:
                # Tolerans penceresi içinde bağlandı → flap, iptal et
                logger.debug(
                    "[%s] CANDIDATE → UP. Bacak Connected geldi (pencere içi, %.1fs), "
                    "tolerans devreye girdi @ %s.",
                    site, elapsed.total_seconds(), event_time,
                )
                state.state = "UP"
                state.candidate_since = None
            else:
                # Tolerans penceresi geçtikten SONRA Connected geldi:
                # Aslında DOWN başlamıştı, şimdi Connected ile bitti
                rec = OutageRecord(
                    site=site,
                    start=state.candidate_since,
                    end=event_time,
                )
                outages.append(rec)
                logger.debug(
                    "[%s] CANDIDATE → UP (geç toparlanma). "
                    "Gerçek kesinti: %s → %s (%.2f dk)",
                    site, state.candidate_since, event_time, rec.duration_minutes,
                )
                state.state = "UP"
                state.candidate_since = None

        elif state.all_disconnected():
            # Hâlâ tüm bacaklar down; tolerans penceresi geçti mi kontrol et
            if elapsed >= tolerance:
                # Gerçek DOWN başlıyor; başlangıç = ilk Disconnected anı
                state.state = "DOWN"
                state.down_since = state.candidate_since
                state.candidate_since = None
                logger.debug(
                    "[%s] CANDIDATE → DOWN. Tolerans aşıldı (%.1fs). "
                    "Gerçek kesinti başlangıcı: %s",
                    site, elapsed.total_seconds(), state.down_since,
                )

    elif current_state == "DOWN":
        if state.any_connected():
            # En az 1 bacak tekrar bağlandı → kesinti bitti
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

