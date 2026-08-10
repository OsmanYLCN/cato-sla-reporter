import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from engine.state_machine import detect_outages, OutageRecord
from engine.leg_detector import detect_legs
from preprocessing.transformer import transform
from config.settings import COL_SITE, COL_TIME, COL_EVENT, COL_IFACE, COL_ROLE, TIMEZONE

_TZ = ZoneInfo(TIMEZONE)

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
    df = pd.DataFrame(events)
    df[COL_TIME] = pd.to_datetime(df[COL_TIME])
    if df[COL_TIME].dt.tz is None:
        df[COL_TIME] = df[COL_TIME].dt.tz_localize(_TZ)
    df = df.sort_values(COL_TIME).reset_index(drop=True)
    leg_map = detect_legs(df)
    return df, leg_map


class TestSingleLegOutage:
    def test_single_leg_down_is_site_down(self):
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
        t_down = datetime(2026, 7, 15, 8, 0, 0, tzinfo=_TZ)
        t_up   = datetime(2026, 7, 15, 9, 30, 0, tzinfo=_TZ)

        events = [
            _make_event("SiteB", t_down, "Disconnected", "WAN1", "primary"),
            _make_event("SiteB", t_up,   "Connected",    "WAN1", "primary"),
        ]
        df, leg_map = _prepare(events)
        outages = detect_outages(df, leg_map, PERIOD_START, PERIOD_END)

        assert len(outages) == 1
        assert outages[0].duration_minutes == pytest.approx(90.0, abs=0.1)


class TestDualLegSite:
    def test_single_leg_down_is_not_site_down(self):
        t_down = datetime(2026, 7, 10, 10, 0, 0, tzinfo=_TZ)
        t_up   = datetime(2026, 7, 10, 11, 0, 0, tzinfo=_TZ)

        events = [
            _make_event("SiteC", t_down, "Disconnected", "WAN1", "primary"),
            _make_event("SiteC", t_up,   "Connected",    "WAN1", "primary"),
        ]
        df, leg_map = _prepare(events)
        leg_map["SiteC"] = frozenset({("WAN1", "primary"), ("WAN2", "secondary")})

        outages = detect_outages(df, leg_map, PERIOD_START, PERIOD_END)
        assert len(outages) == 0

    def test_both_legs_down_is_site_down(self):
        t_wan1_down = datetime(2026, 7, 10, 10, 0, 0, tzinfo=_TZ)
        t_wan2_down = datetime(2026, 7, 10, 10, 0, 5, tzinfo=_TZ)
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
    def test_flap_within_window_not_counted(self):
        t_down = datetime(2026, 7, 10, 10, 0, 0, tzinfo=_TZ)
        t_up   = datetime(2026, 7, 10, 10, 0, 10, tzinfo=_TZ)

        events = [
            _make_event("SiteE", t_down, "Disconnected", "WAN1", "primary"),
            _make_event("SiteE", t_up,   "Connected",    "WAN1", "primary"),
        ]
        df, leg_map = _prepare(events)
        outages = detect_outages(df, leg_map, PERIOD_START, PERIOD_END)
        assert len(outages) == 0

    def test_outage_beyond_window_is_counted(self):
        t_down = datetime(2026, 7, 10, 10, 0, 0, tzinfo=_TZ)
        t_up   = datetime(2026, 7, 10, 10, 1, 30, tzinfo=_TZ)

        events = [
            _make_event("SiteF", t_down, "Disconnected", "WAN1", "primary"),
            _make_event("SiteF", t_up,   "Connected",    "WAN1", "primary"),
        ]
        df, leg_map = _prepare(events)
        outages = detect_outages(df, leg_map, PERIOD_START, PERIOD_END)
        assert len(outages) == 1


class TestOpenOutage:
    def test_open_outage_closed_at_period_end(self):
        t_down = datetime(2026, 7, 31, 22, 0, 0, tzinfo=_TZ)

        events = [
            _make_event("SiteG", t_down, "Disconnected", "WAN1", "primary"),
        ]
        df, leg_map = _prepare(events)
        outages = detect_outages(df, leg_map, PERIOD_START, PERIOD_END)

        assert len(outages) == 1
        assert outages[0].end == PERIOD_END
        assert outages[0].start == t_down


class TestMultipleOutages:
    def test_multiple_outages_counted_separately(self):
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
    def test_empty_period_returns_empty_list(self):
        t_down = datetime(2026, 6, 1, 10, 0, 0, tzinfo=_TZ)
        t_up   = datetime(2026, 6, 1, 11, 0, 0, tzinfo=_TZ)

        events = [
            _make_event("SiteI", t_down, "Disconnected", "WAN1", "primary"),
            _make_event("SiteI", t_up,   "Connected",    "WAN1", "primary"),
        ]
        df, leg_map = _prepare(events)
        outages = detect_outages(df, leg_map, PERIOD_START, PERIOD_END)
        assert len(outages) == 0
