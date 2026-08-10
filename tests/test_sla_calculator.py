"""
tests/test_sla_calculator.py
=============================
engine/sla_calculator.py için birim testler.

Test senaryoları:
    - Sıfır kesintili site → %100 / Passed
    - Kısa kesinti → Yüksek Availability / Passed
    - SLA eşiğini geçen kesinti → Failed
    - Eşik sınır değeri (%99.90) → Passed (eşik dahil)
    - Dönem dakikasını aşan downtime → Aşım koruması
    - Geçersiz period_months → ValueError
    - Logsuz site (all_sites içinde ama outages yok) → %100 / Passed
"""

import pytest
from engine.sla_calculator import calculate_sla, COL_OUT_AVAIL, COL_OUT_SLA, COL_OUT_COUNT
from engine.state_machine import OutageRecord
from datetime import datetime
from zoneinfo import ZoneInfo
from config.settings import TIMEZONE, PERIOD_MINUTES

_TZ = ZoneInfo(TIMEZONE)


def _make_outage(site: str, start_dt: datetime, duration_minutes: float) -> OutageRecord:
    from datetime import timedelta
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    return OutageRecord(site=site, start=start_dt, end=end_dt)


class TestNoOutage:
    """Kesintisiz site testleri."""

    def test_zero_downtime_is_100_percent(self):
        """Hiç kesintisi olmayan site %100 Availability ve Passed olmalı."""
        result = calculate_sla(outages=[], all_sites=["SiteA"], period_months=1)
        row = result[result["Site Name"] == "SiteA"].iloc[0]
        assert row[COL_OUT_AVAIL] == pytest.approx(100.0, abs=0.0001)
        assert row[COL_OUT_SLA] == "Passed"

    def test_zero_outage_count(self):
        """Hiç kesintisi olmayan sitenin kesinti sayısı 0 olmalı."""
        result = calculate_sla(outages=[], all_sites=["SiteA"], period_months=1)
        row = result[result["Site Name"] == "SiteA"].iloc[0]
        assert row[COL_OUT_COUNT] == 0


class TestAvailabilityFormula:
    """Availability formülü testleri."""

    def test_one_hour_outage_1month(self):
        """60 dk kesinti: (43200 - 60) / 43200 * 100 = 99.8611..."""
        t = datetime(2026, 7, 10, 10, 0, 0, tzinfo=_TZ)
        outage = _make_outage("SiteB", t, 60.0)
        result = calculate_sla(outages=[outage], all_sites=["SiteB"], period_months=1)
        row = result[result["Site Name"] == "SiteB"].iloc[0]
        expected = ((43200 - 60) / 43200) * 100
        assert row[COL_OUT_AVAIL] == pytest.approx(expected, abs=0.0001)

    def test_sla_failed_below_threshold(self):
        """Availability < 99.90 olunca Failed olmalı."""
        # 99.90 altına düşürecek kadar downtime
        # 43200 * (1 - 0.999) = 43.2 dk → %99.90 = limit
        # 50 dk → %99.8842 → Failed
        t = datetime(2026, 7, 10, 10, 0, 0, tzinfo=_TZ)
        outage = _make_outage("SiteC", t, 50.0)
        result = calculate_sla(outages=[outage], all_sites=["SiteC"], period_months=1)
        row = result[result["Site Name"] == "SiteC"].iloc[0]
        assert row[COL_OUT_SLA] == "Failed"

    def test_sla_passed_at_threshold(self):
        """Availability tam eşikte (%99.90) ise Passed olmalı."""
        # 43200 * 0.001 = 43.2 dk downtime → Availability = 99.9000% (eşik)
        t = datetime(2026, 7, 10, 10, 0, 0, tzinfo=_TZ)
        outage = _make_outage("SiteD", t, 43.2)
        result = calculate_sla(outages=[outage], all_sites=["SiteD"], period_months=1)
        row = result[result["Site Name"] == "SiteD"].iloc[0]
        assert row[COL_OUT_SLA] == "Passed"

    def test_3month_period_uses_correct_minutes(self):
        """3 aylık dönemde 129.600 dk kullanılmalı."""
        t = datetime(2026, 7, 10, 10, 0, 0, tzinfo=_TZ)
        outage = _make_outage("SiteE", t, 60.0)
        result = calculate_sla(outages=[outage], all_sites=["SiteE"], period_months=3)
        row = result[result["Site Name"] == "SiteE"].iloc[0]
        expected = ((129_600 - 60) / 129_600) * 100
        assert row[COL_OUT_AVAIL] == pytest.approx(expected, abs=0.0001)


class TestOverflowProtection:
    """Aşım koruması testleri."""

    def test_downtime_capped_at_period_minutes(self):
        """Downtime toplam dönem dakikasını aşarsa, Availability 0'dan küçük olmamalı."""
        t = datetime(2026, 7, 10, 10, 0, 0, tzinfo=_TZ)
        # Aşırı uzun 2 kesinti (toplam > 43200 dk)
        o1 = _make_outage("SiteF", t, 30_000.0)
        o2 = _make_outage("SiteF", t, 20_000.0)
        result = calculate_sla(outages=[o1, o2], all_sites=["SiteF"], period_months=1)
        row = result[result["Site Name"] == "SiteF"].iloc[0]
        assert row[COL_OUT_AVAIL] >= 0.0


class TestInvalidPeriod:
    """Geçersiz dönem parametresi testleri."""

    def test_invalid_period_raises_value_error(self):
        """Geçersiz period_months için ValueError fırlatılmalı."""
        with pytest.raises(ValueError, match="Geçersiz rapor dönemi"):
            calculate_sla(outages=[], all_sites=["SiteA"], period_months=2)


class TestNoLogSite:
    """Logsuz site (all_sites içinde ama outages yok) testleri."""

    def test_site_without_logs_is_100_percent(self):
        """Logda geçmeyen ama all_sites'te olan site %100 Availability almalı."""
        t = datetime(2026, 7, 10, 10, 0, 0, tzinfo=_TZ)
        outage = _make_outage("SiteA", t, 60.0)
        result = calculate_sla(
            outages=[outage],
            all_sites=["SiteA", "SiteB_NoLog"],
            period_months=1,
        )
        row = result[result["Site Name"] == "SiteB_NoLog"].iloc[0]
        assert row[COL_OUT_AVAIL] == pytest.approx(100.0)
        assert row[COL_OUT_SLA] == "Passed"
