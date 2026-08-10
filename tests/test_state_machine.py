"""
tests/test_state_machine.py
============================
engine/state_machine.py için birim testler.

Test senaryoları:
    - Tek bacaklı site: 1 bacak kopunca DOWN
    - Çift bacaklı site: Sadece 1 bacak kopunca DOWN DEĞİL
    - Çift bacaklı site: Her iki bacak kopunca GERÇEK DOWN
    - 30s tolerans penceresi içinde geri dönen bacak → flap (DOWN sayılmaz)
    - 30s tolerans penceresini aşan kesinti → DOWN sayılır
    - Dönem sonunda açık kesinti → dönem sonuna kadar hesaplanır
    - Logsuz dönem → boş liste
"""

import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from engine.state_machine import detect_outages, OutageRecord
from engine.leg_detector import detect_legs
from preprocessing.transformer import transform
from config.settings import COL_SITE, COL_TIME, COL_EVENT, COL_IFACE, COL_ROLE, TIMEZONE

_TZ = ZoneInfo(TIMEZONE)

# Sabit test dönemi
PERIOD_START = datetime(2026, 7, 1, 0, 0, 0, tzinfo=_TZ)
PERIOD_END   = datetime(2026, 7, 31, 23, 59, 59, tzinfo=_TZ)


def _make_event(site: str, t: datetime, event: str, iface: str, role: str) -> dict:
    return {
        COL_SITE:  site,
        COL_TIME:  t,
        COL_EVENT: event,
        COL_IFACE: iface,
        COL_ROLE:  role,
    }


def _prepare(events: list[dict]) -> tuple[pd.DataFrame, dict]:
    """Ham olaylardan DataFrame ve leg_map üretir."""
    df = pd.DataFrame(events)
    # datetime nesneleri zaten TZ-aware (tzinfo=_TZ); pd.to_datetime ile koru
    df[COL_TIME] = pd.to_datetime(df[COL_TIME])
    # Eğer tz-naive gelirse localize et, değilse olduğu gibi bırak
    if df[COL_TIME].dt.tz is None:
        df[COL_TIME] = df[COL_TIME].dt.tz_localize(_TZ)
    df = df.sort_values(COL_TIME).reset_index(drop=True)
    leg_map = detect_legs(df)
    return df, leg_map


class TestSingleLegOutage:
    """Tek bacaklı site kesinti testleri."""

    def test_single_leg_down_is_site_down(self):
        """Tek bacaklı sitede bacak kopunca site DOWN olmalı."""
        t_down = datetime(2026, 7, 10, 10, 0, 0, tzinfo=_TZ)
        t_up   = datetime(2026, 7, 10, 10, 45, 0, tzinfo=_TZ)

        events = [
            _make_event("SiteA", t_down, "Disconnected", "WAN1", "primary"),
            _make_event("SiteA", t_up,   "Connected",    "WAN1", "primary"),
        ]
        df, leg_map = _prepare(events)
        outages = detect_outages(df, leg_map, PERIOD_START, PERIOD_END)

        assert len(outages) == 1
        assert outages[0].site == "SiteA"
        assert abs((outages[0].end - outages[0].start).total_seconds() - 45 * 60) < 60

    def test_outage_duration_correct(self):
        """Kesinti süresinin dakika olarak doğru hesaplanması."""
        t_down = datetime(2026, 7, 15, 8, 0, 0, tzinfo=_TZ)
        t_up   = datetime(2026, 7, 15, 9, 30, 0, tzinfo=_TZ)  # 90 dk

        events = [
            _make_event("SiteB", t_down, "Disconnected", "WAN1", "primary"),
            _make_event("SiteB", t_up,   "Connected",    "WAN1", "primary"),
        ]
        df, leg_map = _prepare(events)
        outages = detect_outages(df, leg_map, PERIOD_START, PERIOD_END)

        assert len(outages) == 1
        assert outages[0].duration_minutes == pytest.approx(90.0, abs=0.1)


class TestDualLegSite:
    """Çift bacaklı site testleri."""

    def test_single_leg_down_is_not_site_down(self):
        """Çift bacaklı sitede yalnızca 1 bacak kopunca site DOWN sayılmamalı."""
        t_down = datetime(2026, 7, 10, 10, 0, 0, tzinfo=_TZ)
        t_up   = datetime(2026, 7, 10, 11, 0, 0, tzinfo=_TZ)

        events = [
            _make_event("SiteC", t_down, "Disconnected", "WAN1", "primary"),
            _make_event("SiteC", t_up,   "Connected",    "WAN1", "primary"),
        ]
        # WAN2 hiç olay üretmedi; leg_map'e eklenirse test geçersiz, bu yüzden
        # Manuel olarak WAN2'yi leg_map'e ekliyoruz
        df, leg_map = _prepare(events)
        # Çift bacak simülasyonu için leg_map'i manuel genişlet
        leg_map["SiteC"] = frozenset({("WAN1", "primary"), ("WAN2", "secondary")})
        # WAN2'nin başlangıç durumu Connected (state machine default)

        outages = detect_outages(df, leg_map, PERIOD_START, PERIOD_END)
        assert len(outages) == 0, "Tek bacak kopması site DOWN sayılmamalı"

    def test_both_legs_down_is_site_down(self):
        """Her iki bacak da kopunca site DOWN sayılmalı."""
        t_wan1_down = datetime(2026, 7, 10, 10, 0, 0, tzinfo=_TZ)
        t_wan2_down = datetime(2026, 7, 10, 10, 0, 5, tzinfo=_TZ)   # 5s fark (tolerans içinde)
        t_wan1_up   = datetime(2026, 7, 10, 11, 0, 0, tzinfo=_TZ)

        events = [
            _make_event("SiteD", t_wan1_down, "Disconnected", "WAN1", "primary"),
            _make_event("SiteD", t_wan2_down, "Disconnected", "WAN2", "secondary"),
            _make_event("SiteD", t_wan1_up,   "Connected",    "WAN1", "primary"),
        ]
        df, leg_map = _prepare(events)
        outages = detect_outages(df, leg_map, PERIOD_START, PERIOD_END)

        assert len(outages) == 1
        assert outages[0].site == "SiteD"


class TestCorrelationWindow:
    """30 saniyelik tolerans penceresi testleri."""

    def test_flap_within_window_not_counted(self):
        """30s içinde geri dönen bacak flap (geçici) sayılmalı; DOWN üretilmemeli."""
        t_down = datetime(2026, 7, 10, 10, 0, 0, tzinfo=_TZ)
        t_up   = datetime(2026, 7, 10, 10, 0, 10, tzinfo=_TZ)   # 10s sonra geri döndü

        events = [
            _make_event("SiteE", t_down, "Disconnected", "WAN1", "primary"),
            _make_event("SiteE", t_up,   "Connected",    "WAN1", "primary"),
        ]
        df, leg_map = _prepare(events)
        outages = detect_outages(df, leg_map, PERIOD_START, PERIOD_END)
        assert len(outages) == 0, "30s içindeki flap DOWN sayılmamalı"

    def test_outage_beyond_window_is_counted(self):
        """30s toleransı aşan kesinti DOWN olarak kaydedilmeli."""
        t_down = datetime(2026, 7, 10, 10, 0, 0, tzinfo=_TZ)
        t_up   = datetime(2026, 7, 10, 10, 1, 30, tzinfo=_TZ)   # 90s sonra geri döndü

        events = [
            _make_event("SiteF", t_down, "Disconnected", "WAN1", "primary"),
            _make_event("SiteF", t_up,   "Connected",    "WAN1", "primary"),
        ]
        df, leg_map = _prepare(events)
        outages = detect_outages(df, leg_map, PERIOD_START, PERIOD_END)
        assert len(outages) == 1


class TestOpenOutage:
    """Dönem sonunda açık kalan kesinti testleri."""

    def test_open_outage_closed_at_period_end(self):
        """Dönem sonunda hâlâ DOWN olan sitenin bitiş zamanı dönem sonu olmalı."""
        t_down = datetime(2026, 7, 31, 22, 0, 0, tzinfo=_TZ)  # Son gün, gece

        events = [
            _make_event("SiteG", t_down, "Disconnected", "WAN1", "primary"),
            # Hiç Connected gelmedi
        ]
        df, leg_map = _prepare(events)
        outages = detect_outages(df, leg_map, PERIOD_START, PERIOD_END)

        assert len(outages) == 1
        assert outages[0].end == PERIOD_END
        assert outages[0].start == t_down


class TestMultipleOutages:
    """Birden fazla kesinti testi."""

    def test_multiple_outages_counted_separately(self):
        """Aynı sitede 2 ayrı kesinti 2 ayrı kayıt olarak sayılmalı."""
        events = [
            _make_event("SiteH", datetime(2026, 7, 5, 8, 0, 0, tzinfo=_TZ),  "Disconnected", "WAN1", "primary"),
            _make_event("SiteH", datetime(2026, 7, 5, 9, 0, 0, tzinfo=_TZ),  "Connected",    "WAN1", "primary"),
            _make_event("SiteH", datetime(2026, 7, 15, 8, 0, 0, tzinfo=_TZ), "Disconnected", "WAN1", "primary"),
            _make_event("SiteH", datetime(2026, 7, 15, 9, 30, 0, tzinfo=_TZ),"Connected",    "WAN1", "primary"),
        ]
        df, leg_map = _prepare(events)
        outages = detect_outages(df, leg_map, PERIOD_START, PERIOD_END)
        assert len(outages) == 2


class TestNoLogs:
    """Log kaydı olmayan dönem testi."""

    def test_empty_period_returns_empty_list(self):
        """Dönem dışında log olan site için boş liste dönmeli."""
        # Dönemin dışında
        t_down = datetime(2026, 6, 1, 10, 0, 0, tzinfo=_TZ)   # Haziran
        t_up   = datetime(2026, 6, 1, 11, 0, 0, tzinfo=_TZ)

        events = [
            _make_event("SiteI", t_down, "Disconnected", "WAN1", "primary"),
            _make_event("SiteI", t_up,   "Connected",    "WAN1", "primary"),
        ]
        df, leg_map = _prepare(events)
        outages = detect_outages(df, leg_map, PERIOD_START, PERIOD_END)
        assert len(outages) == 0
