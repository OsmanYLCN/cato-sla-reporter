"""
tests/test_transformer.py
==========================
preprocessing/transformer.py için birim testler.

Test senaryoları:
    - UTC → Istanbul dönüşümü doğruluğu
    - Null değerlerin filtrelenmesi
    - Boş string değerlerin temizlenmesi
    - Duplicate satırların kaldırılması
    - Zaman sıralama doğruluğu
    - Geçersiz zaman damgalarının atılması
"""

import pytest
import pandas as pd
from datetime import timezone

from preprocessing.transformer import transform
from config.settings import COL_TIME, COL_SITE, COL_EVENT, COL_IFACE, COL_ROLE, TIMEZONE
from zoneinfo import ZoneInfo

_TZ = ZoneInfo(TIMEZONE)


def _make_df(**kwargs) -> pd.DataFrame:
    """Test için minimal geçerli DataFrame oluşturur."""
    base = {
        COL_SITE:  ["Site-A", "Site-A"],
        COL_TIME:  ["2026-07-01 10:00:00", "2026-07-01 11:00:00"],
        COL_EVENT: ["Disconnected", "Connected"],
        COL_IFACE: ["WAN1", "WAN1"],
        COL_ROLE:  ["primary", "primary"],
    }
    base.update(kwargs)
    return pd.DataFrame(base)


class TestUtcToIstanbul:
    """UTC → Europe/Istanbul dönüşüm testleri."""

    def test_utc_offset_applied(self):
        """UTC 10:00 → Istanbul 13:00 (UTC+3) olmalı."""
        df = pd.DataFrame([{
            COL_SITE: "Site-A",
            COL_TIME: "2026-07-01 10:00:00",
            COL_EVENT: "Connected",
            COL_IFACE: "WAN1",
            COL_ROLE: "primary",
        }])
        result = transform(df)
        ts = result[COL_TIME].iloc[0]
        assert ts.hour == 13, f"Beklenen 13, gelen: {ts.hour}"
        assert ts.tzinfo is not None

    def test_timezone_name(self):
        """Dönüştürülmüş zaman dilimi Europe/Istanbul olmalı."""
        df = _make_df()
        result = transform(df)
        tz_name = str(result[COL_TIME].iloc[0].tzinfo)
        assert "Istanbul" in tz_name or "Europe" in tz_name or tz_name == TIMEZONE


class TestNullFiltering:
    """Null ve boş değer filtreleme testleri."""

    def test_null_site_dropped(self):
        """src_site_name null olan satırlar kaldırılmalı."""
        df = _make_df(**{COL_SITE: [None, "Site-A"]})
        result = transform(df)
        assert len(result) == 1
        assert result[COL_SITE].iloc[0] == "Site-A"

    def test_null_event_dropped(self):
        """event_sub_type null olan satırlar kaldırılmalı."""
        df = _make_df(**{COL_EVENT: [None, "Connected"]})
        result = transform(df)
        assert len(result) == 1

    def test_empty_string_site_dropped(self):
        """Boş string site adı olan satırlar kaldırılmalı."""
        df = _make_df(**{COL_SITE: ["", "Site-A"]})
        result = transform(df)
        assert len(result) == 1

    def test_invalid_timestamp_dropped(self):
        """Parse edilemeyen zaman damgaları olan satırlar atılmalı."""
        df = _make_df(**{COL_TIME: ["INVALID_DATE", "2026-07-01 10:00:00"]})
        result = transform(df)
        assert len(result) == 1


class TestDeduplication:
    """Duplicate satır temizleme testleri."""

    def test_exact_duplicates_removed(self):
        """Birebir aynı satırlardan biri kaldırılmalı."""
        row = {
            COL_SITE: "Site-A",
            COL_TIME: "2026-07-01 10:00:00",
            COL_EVENT: "Connected",
            COL_IFACE: "WAN1",
            COL_ROLE: "primary",
        }
        df = pd.DataFrame([row, row])
        result = transform(df)
        assert len(result) == 1


class TestSorting:
    """Zaman sıralama testleri."""

    def test_sorted_ascending(self):
        """Çıktı DataFrame'i zaman sırasına göre ascending sıralı olmalı."""
        df = _make_df(**{
            COL_TIME: ["2026-07-01 12:00:00", "2026-07-01 08:00:00"],
            COL_EVENT: ["Connected", "Disconnected"],
        })
        result = transform(df)
        times = result[COL_TIME].tolist()
        assert times[0] < times[1], "Satırlar zamanla artan sırada olmalı"


class TestEmptyDataFrame:
    """Boş DataFrame davranışı."""

    def test_empty_df_returned_as_is(self):
        """Boş DataFrame dönüştürme yapılmadan döndürülmeli."""
        df = pd.DataFrame(columns=[COL_SITE, COL_TIME, COL_EVENT, COL_IFACE, COL_ROLE])
        result = transform(df)
        assert result.empty
