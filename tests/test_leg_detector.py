"""
tests/test_leg_detector.py
===========================
engine/leg_detector.py için birim testler.

Test senaryoları:
    - Tek bacaklı site tespiti
    - Çift bacaklı site (WAN1 + WAN2) tespiti
    - Çoklu site eş zamanlı tespiti
    - Boş DataFrame davranışı
"""

import pandas as pd
import pytest

from engine.leg_detector import detect_legs
from config.settings import COL_SITE, COL_IFACE, COL_ROLE, COL_TIME, COL_EVENT


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Test verisi oluşturur."""
    return pd.DataFrame(rows)


class TestSingleLeg:
    """Tek bacaklı site testleri."""

    def test_single_leg_detected(self):
        """Tek (interface, role) çifti doğru tespit edilmeli."""
        df = _make_df([
            {COL_SITE: "SiteA", COL_IFACE: "WAN1", COL_ROLE: "primary",
             COL_TIME: "2026-07-01", COL_EVENT: "Connected"},
            {COL_SITE: "SiteA", COL_IFACE: "WAN1", COL_ROLE: "primary",
             COL_TIME: "2026-07-02", COL_EVENT: "Disconnected"},
        ])
        result = detect_legs(df)
        assert "SiteA" in result
        assert result["SiteA"] == frozenset({("WAN1", "primary")})
        assert len(result["SiteA"]) == 1


class TestMultiLeg:
    """Çift bacaklı site testleri."""

    def test_dual_wan_detected(self):
        """WAN1+WAN2 olan site için her iki bacak tespit edilmeli."""
        df = _make_df([
            {COL_SITE: "SiteB", COL_IFACE: "WAN1", COL_ROLE: "primary",
             COL_TIME: "2026-07-01", COL_EVENT: "Connected"},
            {COL_SITE: "SiteB", COL_IFACE: "WAN2", COL_ROLE: "secondary",
             COL_TIME: "2026-07-01", COL_EVENT: "Disconnected"},
        ])
        result = detect_legs(df)
        assert result["SiteB"] == frozenset({
            ("WAN1", "primary"),
            ("WAN2", "secondary"),
        })
        assert len(result["SiteB"]) == 2

    def test_ha_socket_legs(self):
        """PRIMARY1 + PRIMARY2 HA çiftini tespit etmeli."""
        df = _make_df([
            {COL_SITE: "SiteC", COL_IFACE: "PRIMARY1", COL_ROLE: "primary",
             COL_TIME: "2026-07-01", COL_EVENT: "Connected"},
            {COL_SITE: "SiteC", COL_IFACE: "PRIMARY2", COL_ROLE: "secondary",
             COL_TIME: "2026-07-01", COL_EVENT: "Connected"},
        ])
        result = detect_legs(df)
        assert ("PRIMARY1", "primary") in result["SiteC"]
        assert ("PRIMARY2", "secondary") in result["SiteC"]


class TestMultipleSites:
    """Çoklu site testleri."""

    def test_multiple_sites_independent(self):
        """Birden fazla site bağımsız olarak tespit edilmeli."""
        df = _make_df([
            {COL_SITE: "SiteA", COL_IFACE: "WAN1", COL_ROLE: "primary",
             COL_TIME: "2026-07-01", COL_EVENT: "Connected"},
            {COL_SITE: "SiteB", COL_IFACE: "WAN1", COL_ROLE: "primary",
             COL_TIME: "2026-07-01", COL_EVENT: "Connected"},
            {COL_SITE: "SiteB", COL_IFACE: "WAN2", COL_ROLE: "secondary",
             COL_TIME: "2026-07-01", COL_EVENT: "Connected"},
        ])
        result = detect_legs(df)
        assert len(result) == 2
        assert len(result["SiteA"]) == 1
        assert len(result["SiteB"]) == 2


class TestEdgeCases:
    """Kenar durum testleri."""

    def test_empty_dataframe_returns_empty_dict(self):
        """Boş DataFrame için boş dict dönmeli."""
        df = pd.DataFrame(columns=[COL_SITE, COL_IFACE, COL_ROLE, COL_TIME, COL_EVENT])
        result = detect_legs(df)
        assert result == {}

    def test_duplicate_events_single_leg(self):
        """Aynı bacağa ait çok sayıda olay tek bacak olarak sayılmalı."""
        df = _make_df([
            {COL_SITE: "SiteD", COL_IFACE: "WAN1", COL_ROLE: "primary",
             COL_TIME: f"2026-07-0{i}", COL_EVENT: "Connected"}
            for i in range(1, 6)
        ])
        result = detect_legs(df)
        assert len(result["SiteD"]) == 1
