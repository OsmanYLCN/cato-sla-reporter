import pandas as pd
from datetime import timezone
from zoneinfo import ZoneInfo

from preprocessing.transformer import transform
from config.settings import COL_TIME, COL_SITE, COL_EVENT, COL_IFACE, COL_ROLE, TIMEZONE

_TZ = ZoneInfo(TIMEZONE)


def _make_df(**kwargs) -> pd.DataFrame:
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
    def test_utc_offset_applied(self):
        df = pd.DataFrame([{
            COL_SITE: "Site-A",
            COL_TIME: "2026-07-01 10:00:00",
            COL_EVENT: "Connected",
            COL_IFACE: "WAN1",
            COL_ROLE: "primary",
        }])
        result = transform(df)
        ts = result[COL_TIME].iloc[0]
        assert ts.hour == 13
        assert ts.tzinfo is not None

    def test_timezone_name(self):
        df = _make_df()
        result = transform(df)
        tz_name = str(result[COL_TIME].iloc[0].tzinfo)
        assert "Istanbul" in tz_name or "Europe" in tz_name or tz_name == TIMEZONE


class TestNullFiltering:
    def test_null_site_dropped(self):
        df = _make_df(**{COL_SITE: [None, "Site-A"]})
        result = transform(df)
        assert len(result) == 1
        assert result[COL_SITE].iloc[0] == "Site-A"

    def test_null_event_dropped(self):
        df = _make_df(**{COL_EVENT: [None, "Connected"]})
        result = transform(df)
        assert len(result) == 1

    def test_empty_string_site_dropped(self):
        df = _make_df(**{COL_SITE: ["", "Site-A"]})
        result = transform(df)
        assert len(result) == 1

    def test_invalid_timestamp_dropped(self):
        df = _make_df(**{COL_TIME: ["INVALID_DATE", "2026-07-01 10:00:00"]})
        result = transform(df)
        assert len(result) == 1


class TestDeduplication:
    def test_exact_duplicates_removed(self):
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

    def test_consecutive_duplicate_events_removed(self):
        rows = [
            {COL_SITE: "Site-A", COL_TIME: "2026-07-01 10:00:00", COL_EVENT: "Disconnected", COL_IFACE: "WAN1", COL_ROLE: "primary"},
            {COL_SITE: "Site-A", COL_TIME: "2026-07-01 10:05:00", COL_EVENT: "Disconnected", COL_IFACE: "WAN1", COL_ROLE: "primary"}, # consecutive dup
            {COL_SITE: "Site-A", COL_TIME: "2026-07-01 11:00:00", COL_EVENT: "Connected",    COL_IFACE: "WAN1", COL_ROLE: "primary"},
            {COL_SITE: "Site-A", COL_TIME: "2026-07-01 11:05:00", COL_EVENT: "Connected",    COL_IFACE: "WAN1", COL_ROLE: "primary"}, # consecutive dup
            {COL_SITE: "Site-A", COL_TIME: "2026-07-01 12:00:00", COL_EVENT: "Disconnected", COL_IFACE: "WAN1", COL_ROLE: "primary"},
        ]
        df = pd.DataFrame(rows)
        result = transform(df)
        assert len(result) == 3
        events = result[COL_EVENT].tolist()
        assert events == ["Disconnected", "Connected", "Disconnected"]


class TestSorting:
    def test_sorted_ascending(self):
        df = _make_df(**{
            COL_TIME: ["2026-07-01 12:00:00", "2026-07-01 08:00:00"],
            COL_EVENT: ["Connected", "Disconnected"],
        })
        result = transform(df)
        times = result[COL_TIME].tolist()
        assert times[0] < times[1]


class TestEmptyDataFrame:
    def test_empty_df_returned_as_is(self):
        df = pd.DataFrame(columns=[COL_SITE, COL_TIME, COL_EVENT, COL_IFACE, COL_ROLE])
        result = transform(df)
        assert result.empty
