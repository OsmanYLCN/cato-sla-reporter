"""
tests/test_cato_api_client.py

CatoApiClient icin birim testler.
Gercek ag baglantisi gerektirmez -- requests.post mock'lanir.
"""
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from config.settings import COL_EVENT, COL_IFACE, COL_ROLE, COL_SITE, COL_TIME, TIMEZONE
from data_ingestion.cato_api_client import CatoApiClient, CatoApiError

_TZ = ZoneInfo(TIMEZONE)
_UTC = ZoneInfo("UTC")


# ---------------------------------------------------------------------------
# Yardimci sabitler
# ---------------------------------------------------------------------------
_FAKE_KEY = "test-api-key"
_FAKE_ACC = "99999"

_PERIOD_START = datetime(2026, 7, 1, 0, 0, 0, tzinfo=_TZ)
_PERIOD_END   = datetime(2026, 7, 31, 23, 59, 59, tzinfo=_TZ)


def _make_record(
    time_iso: str,
    site: str = "Site-A",
    event: str = "Disconnected",
    iface: str = "WAN1",
    role: str  = "primary",
) -> dict:
    """Test icin ham API kaydi olusturur (flatFields yapisi)."""
    return {
        "time": time_iso,
        "fieldsMap": {},
        "flatFields": [
            {"fieldName": "src_site_name",   "value": site},
            {"fieldName": "event_sub_type",  "value": event},
            {"fieldName": "socket_interface","value": iface},
            {"fieldName": "socket_role",     "value": role},
        ],
    }


def _api_response(records: list[dict], marker_in: str | None = None, marker_out: str = "m1") -> dict:
    """Basarili API yaniti dict'i olusturur."""
    return {
        "data": {
            "eventsFeed": {
                "marker": marker_out,
                "fetchedCount": len(records),
                "accounts": [{"records": records}],
            }
        }
    }


def _make_client() -> CatoApiClient:
    return CatoApiClient(api_key=_FAKE_KEY, account_id=_FAKE_ACC)


# ---------------------------------------------------------------------------
# Kimlik dogrulama testleri
# ---------------------------------------------------------------------------
class TestClientInit:
    def test_raises_if_no_api_key(self):
        with pytest.raises(CatoApiError, match="API Key"):
            CatoApiClient(api_key="", account_id=_FAKE_ACC)

    def test_raises_if_no_account_id(self):
        with pytest.raises(CatoApiError, match="Account ID"):
            CatoApiClient(api_key=_FAKE_KEY, account_id="")

    def test_init_success(self):
        client = _make_client()
        assert client is not None


# ---------------------------------------------------------------------------
# Timestamp parse testleri
# ---------------------------------------------------------------------------
class TestParseTimestamp:
    def test_iso_utc_string(self):
        ts = CatoApiClient._parse_timestamp("2026-07-15T10:00:00Z")
        assert ts is not None
        assert ts.tzinfo is not None
        # UTC+3 olarak gelmeli (Istanbul)
        assert ts.hour == 13

    def test_iso_with_offset(self):
        ts = CatoApiClient._parse_timestamp("2026-07-15T10:00:00+00:00")
        assert ts is not None
        assert ts.hour == 13

    def test_unix_milliseconds(self):
        # 2026-07-15 10:00:00 UTC = 1752573600000 ms
        ts = CatoApiClient._parse_timestamp("1752573600000")
        assert ts is not None

    def test_unix_seconds(self):
        ts = CatoApiClient._parse_timestamp("1752573600")
        assert ts is not None

    def test_invalid_returns_none(self):
        assert CatoApiClient._parse_timestamp("NOT_A_DATE") is None

    def test_empty_returns_none(self):
        assert CatoApiClient._parse_timestamp("") is None

    def test_none_returns_none(self):
        assert CatoApiClient._parse_timestamp(None) is None


# ---------------------------------------------------------------------------
# fetch_events & pagination testleri
# ---------------------------------------------------------------------------
class TestFetchEvents:
    def test_single_page_returns_dataframe(self):
        record = _make_record("2026-07-10T08:00:00Z")
        response = _api_response([record], marker_out="m1")
        # Ikinci cagri: fetchedCount=0 ile pagination biter
        terminal = _api_response([], marker_out="m1")

        with patch("requests.post") as mock_post:
            mock_post.side_effect = [
                MagicMock(status_code=200, raise_for_status=lambda: None,
                          json=lambda: response),
                MagicMock(status_code=200, raise_for_status=lambda: None,
                          json=lambda: terminal),
            ]
            client = _make_client()
            df = client.fetch_events(_PERIOD_START, _PERIOD_END)

        assert not df.empty
        assert list(df.columns) == [COL_SITE, COL_TIME, COL_EVENT, COL_IFACE, COL_ROLE]
        assert df[COL_SITE].iloc[0] == "Site-A"
        assert df[COL_EVENT].iloc[0] == "Disconnected"

    def test_empty_api_response_returns_empty_df(self):
        response = _api_response([], marker_out=None)
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                raise_for_status=lambda: None,
                json=lambda: response,
            )
            client = _make_client()
            df = client.fetch_events(_PERIOD_START, _PERIOD_END)

        assert df.empty
        assert COL_SITE in df.columns

    def test_records_outside_period_are_filtered(self):
        # Donem disinda bir kayit: Ekim 2026
        record = _make_record("2026-10-01T10:00:00Z")
        response = _api_response([record], marker_out="m1")
        terminal = _api_response([], marker_out="m1")

        with patch("requests.post") as mock_post:
            mock_post.side_effect = [
                MagicMock(status_code=200, raise_for_status=lambda: None,
                          json=lambda: response),
                MagicMock(status_code=200, raise_for_status=lambda: None,
                          json=lambda: terminal),
            ]
            client = _make_client()
            df = client.fetch_events(_PERIOD_START, _PERIOD_END)

        assert df.empty

    def test_multiple_sites_in_response(self):
        records = [
            _make_record("2026-07-05T10:00:00Z", site="Site-A"),
            _make_record("2026-07-06T10:00:00Z", site="Site-B"),
            _make_record("2026-07-07T10:00:00Z", site="Site-A", event="Connected"),
        ]
        response = _api_response(records, marker_out="m1")
        terminal = _api_response([], marker_out="m1")

        with patch("requests.post") as mock_post:
            mock_post.side_effect = [
                MagicMock(status_code=200, raise_for_status=lambda: None,
                          json=lambda: response),
                MagicMock(status_code=200, raise_for_status=lambda: None,
                          json=lambda: terminal),
            ]
            client = _make_client()
            df = client.fetch_events(_PERIOD_START, _PERIOD_END)

        assert len(df) == 3
        assert set(df[COL_SITE]) == {"Site-A", "Site-B"}


# ---------------------------------------------------------------------------
# Hata yonetimi testleri
# ---------------------------------------------------------------------------
class TestErrorHandling:
    def test_http_error_raises_cato_api_error(self):
        import requests as req
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        http_exc = req.exceptions.HTTPError(response=mock_resp)

        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                raise_for_status=MagicMock(side_effect=http_exc)
            )
            client = _make_client()
            with pytest.raises(CatoApiError):
                client.fetch_events(_PERIOD_START, _PERIOD_END)

    def test_graphql_errors_in_response_raises(self):
        error_response = {
            "errors": [{"message": "Unauthorized"}],
            "data": None,
        }
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                raise_for_status=lambda: None,
                json=lambda: error_response,
            )
            client = _make_client()
            with pytest.raises(CatoApiError, match="Unauthorized"):
                client.fetch_events(_PERIOD_START, _PERIOD_END)

    def test_connection_error_retries_and_raises(self):
        import requests as req
        with patch("requests.post", side_effect=req.exceptions.ConnectionError("down")):
            with patch("time.sleep"):  # sleep'i atla
                client = _make_client()
                with pytest.raises(CatoApiError, match="basarisiz"):
                    client.fetch_events(_PERIOD_START, _PERIOD_END)

    def test_timeout_retries_and_raises(self):
        import requests as req
        with patch("requests.post", side_effect=req.exceptions.Timeout("timeout")):
            with patch("time.sleep"):
                client = _make_client()
                with pytest.raises(CatoApiError, match="basarisiz"):
                    client.fetch_events(_PERIOD_START, _PERIOD_END)


# ---------------------------------------------------------------------------
# Normallesme testleri
# ---------------------------------------------------------------------------
class TestNormalise:
    def test_missing_site_skips_record(self):
        records = [
            {
                "time": "2026-07-10T08:00:00Z",
                "fieldsMap": {},
                "flatFields": [
                    # site yok
                    {"fieldName": "event_sub_type",  "value": "Disconnected"},
                    {"fieldName": "socket_interface", "value": "WAN1"},
                    {"fieldName": "socket_role",      "value": "primary"},
                ],
            }
        ]
        client = _make_client()
        df = client._normalise(records)
        assert df.empty

    def test_invalid_timestamp_skips_record(self):
        records = [_make_record("INVALID_TS")]
        client = _make_client()
        df = client._normalise(records)
        assert df.empty

    def test_fieldmap_fallback(self):
        """flatFields yoksa fieldsMap'ten okuyabilmeli."""
        records = [
            {
                "time": "2026-07-10T08:00:00Z",
                "fieldsMap": {
                    "src_site_name":    ["Site-Z"],
                    "event_sub_type":   ["Connected"],
                    "socket_interface": ["WAN2"],
                    "socket_role":      ["secondary"],
                },
                "flatFields": [],
            }
        ]
        client = _make_client()
        df = client._normalise(records)
        assert len(df) == 1
        assert df[COL_SITE].iloc[0] == "Site-Z"
        assert df[COL_IFACE].iloc[0] == "WAN2"
