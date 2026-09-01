"""
tests/test_period_resolver.py

resolve_period_dates fonksiyonu icin birim testler.
"""
from datetime import datetime
import pytest

from config.settings import TZ
from main import resolve_period_dates


class TestResolvePeriodDatesAuto:
    def test_auto_1_month_september(self):
        fake_now = datetime(2026, 9, 1, 10, 0, 0, tzinfo=TZ)
        start, end = resolve_period_dates(period_months=1, mode="auto", now=fake_now)
        assert start == datetime(2026, 8, 1, 0, 0, 0, tzinfo=TZ)
        assert end == datetime(2026, 8, 31, 23, 59, 59, 999999, tzinfo=TZ)

    def test_auto_3_months_september(self):
        # 1 Eylulde calistiginda tamamlanmis son 3 takvim ayi: Haziran, Temmuz, Agustos
        fake_now = datetime(2026, 9, 1, 10, 0, 0, tzinfo=TZ)
        start, end = resolve_period_dates(period_months=3, mode="auto", now=fake_now)
        assert start == datetime(2026, 6, 1, 0, 0, 0, tzinfo=TZ)
        assert end == datetime(2026, 8, 31, 23, 59, 59, 999999, tzinfo=TZ)

    def test_auto_3_months_year_boundary(self):
        # 15 Ocak 2027de calistiginda: Ekim 2026, Kasim 2026, Aralik 2026
        fake_now = datetime(2027, 1, 15, 12, 0, 0, tzinfo=TZ)
        start, end = resolve_period_dates(period_months=3, mode="auto", now=fake_now)
        assert start == datetime(2026, 10, 1, 0, 0, 0, tzinfo=TZ)
        assert end == datetime(2026, 12, 31, 23, 59, 59, 999999, tzinfo=TZ)

    def test_auto_3_months_march(self):
        # 1 Mart 2027de calistiginda: Aralik 2026, Ocak 2027, Subat 2027
        fake_now = datetime(2027, 3, 1, 8, 0, 0, tzinfo=TZ)
        start, end = resolve_period_dates(period_months=3, mode="auto", now=fake_now)
        assert start == datetime(2026, 12, 1, 0, 0, 0, tzinfo=TZ)
        assert end == datetime(2027, 2, 28, 23, 59, 59, 999999, tzinfo=TZ)


class TestResolvePeriodDatesManual:
    def test_manual_1_month(self):
        fake_now = datetime(2026, 9, 1, 10, 0, 0, tzinfo=TZ)
        start, end = resolve_period_dates(period_months=1, mode="manual", now=fake_now)
        # 30 gun geriye
        assert (end.date() - start.date()).days == 30

    def test_manual_3_months(self):
        fake_now = datetime(2026, 9, 1, 10, 0, 0, tzinfo=TZ)
        start, end = resolve_period_dates(period_months=3, mode="manual", now=fake_now)
        # 90 gun geriye
        assert (end.date() - start.date()).days == 90


class TestInvalidMode:
    def test_invalid_mode_raises_value_error(self):
        with pytest.raises(ValueError, match="Geçersiz mod"):
            resolve_period_dates(period_months=1, mode="invalid")
