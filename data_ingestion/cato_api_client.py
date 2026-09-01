"""
data_ingestion/cato_api_client.py

Cato Networks GraphQL API istemcisi.

Belirtilen zaman araligindaki connectivity ve socket management event'lerini
marker tabanli pagination ile ceker, mevcut pipeline'in beklettigi DataFrame
formatina donusturur.
"""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from config.settings import (
    CATO_ACCOUNT_ID,
    CATO_API_ENDPOINT,
    CATO_API_KEY,
    CATO_API_MAX_RETRIES,
    CATO_API_PAGE_SIZE,
    CATO_API_RETRY_DELAY_SECONDS,
    CATO_API_TIMEOUT_SECONDS,
    COL_EVENT,
    COL_IFACE,
    COL_ROLE,
    COL_SITE,
    COL_TIME,
    TZ,
)
from utils.logger import get_logger

logger = get_logger(__name__)

_UTC = ZoneInfo("UTC")

# ---------------------------------------------------------------------------
# GraphQL Sorgu Sabiti
# ---------------------------------------------------------------------------
_EVENTS_FEED_QUERY = """
query GetConnectivityEvents(
  $accountIDs: [ID!]!
  $marker:     String
  $filters:    [EventFieldFilterInput]
  $limit:      Int
) {
  eventsFeed(
    accountIDs: $accountIDs
    marker:     $marker
    filters:    $filters
    limit:      $limit
  ) {
    marker
    fetchedCount
    accounts {
      records {
        time
        fieldsMap
        flatFields { fieldName value }
      }
    }
  }
}
"""

# Filtrelenecek olay tipleri
_EVENT_TYPE_FILTERS = [
    {"fieldName": "event_type", "operator": "is", "values": ["Connectivity"]},
]


class CatoApiError(Exception):
    """Cato API'sinden donen hata durumlarini temsil eder."""


class CatoApiClient:
    """
    Cato Networks GraphQL API istemcisi.

    Kullanim:
        client = CatoApiClient()
        df = client.fetch_events(period_start, period_end)
    """

    def __init__(
        self,
        api_key: str | None = None,
        account_id: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        self._api_key    = api_key    or CATO_API_KEY
        self._account_id = account_id or CATO_ACCOUNT_ID
        self._endpoint   = endpoint   or CATO_API_ENDPOINT

        if not self._api_key:
            raise CatoApiError(
                "Cato API Key bulunamadi. "
                ".env dosyasinda CATO_API_KEY tanimlandigini kontrol edin."
            )
        if not self._account_id:
            raise CatoApiError(
                "Cato Account ID bulunamadi. "
                ".env dosyasinda CATO_ACCOUNT_ID tanimlandigini kontrol edin."
            )

        self._headers = {
            "x-api-key":    self._api_key,
            "Content-Type": "application/json",
        }

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def fetch_events(
        self,
        period_start: datetime,
        period_end: datetime,
    ) -> pd.DataFrame:
        """
        Belirtilen zaman araligindaki connectivity event'lerini API'den ceker.

        Dondurulen DataFrame sutunlari mevcut pipeline ile uyumludur:
            COL_SITE  (src_site_name)
            COL_TIME  (time)           -- timezone-aware (Europe/Istanbul)
            COL_EVENT (event_sub_type)
            COL_IFACE (socket_interface)
            COL_ROLE  (socket_role)

        Args:
            period_start: Raporlama doneminin baslangic zamani (tz-aware).
            period_end:   Raporlama doneminin bitis zamani (tz-aware).

        Returns:
            Ham event kayitlarini iceren pd.DataFrame.
        """
        logger.info(
            "Cato API'den event cekimi basladi: %s -> %s",
            period_start.strftime("%Y-%m-%d %H:%M:%S %Z"),
            period_end.strftime("%Y-%m-%d %H:%M:%S %Z"),
        )

        raw_records = self._paginate(period_start=period_start, period_end=period_end)

        if not raw_records:
            logger.warning("API'den hic event kaydi donmedi.")
            return self._empty_dataframe()

        df = self._normalise(raw_records)

        # Zaman araligini istemci tarafinda filtrele
        before_filter = len(df)
        mask = (df[COL_TIME] >= period_start) & (df[COL_TIME] <= period_end)
        df = df[mask].reset_index(drop=True)
        filtered_out = before_filter - len(df)

        if filtered_out > 0:
            logger.debug(
                "%d kayit zaman aralik filtresi sonrasi elendi.", filtered_out
            )

        logger.info(
            "API'den %d ham kayit alindi, zaman filtresinden sonra %d kayit isleme alinacak.",
            before_filter,
            len(df),
        )
        return df

    # -----------------------------------------------------------------------
    # Pagination
    # -----------------------------------------------------------------------

    def _paginate(
        self,
        period_start: datetime,
        period_end: datetime,
    ) -> list[dict]:
        """
        marker tabanli pagination dongusu ile tum sayfalar cekilir.

        Cato eventsFeed bir kuyruk sistemi gibi calisir:
          1. marker=None ile ilk istek -> marker deger alinir
          2. Bu marker ile bir sonraki istek -> yeni marker + records gelir
          3. marker ayni kalana kadar devam edilir (kuyruk sonu)
        """
        all_records: list[dict] = []
        marker: str | None = None
        page = 0

        while True:
            page += 1
            logger.debug("Sayfa %d cekiliyor (marker=%s)...", page, marker or "baslangic")

            response = self._request_with_retry(marker=marker)
            feed = response.get("data", {}).get("eventsFeed", {})

            new_marker    = feed.get("marker")
            fetched_count = feed.get("fetchedCount", 0)
            accounts      = feed.get("accounts", [])

            page_records: list[dict] = []
            for account in accounts:
                page_records.extend(account.get("records", []))

            all_records.extend(page_records)
            logger.debug(
                "Sayfa %d: %d kayit alindi, toplam: %d",
                page, len(page_records), len(all_records),
            )

            # Durdurma kosullari
            if not new_marker or new_marker == marker or fetched_count == 0:
                logger.debug("Pagination tamamlandi. Toplam %d kayit.", len(all_records))
                break

            # Erken durdurma: son kayit period_end'i gecti mi
            if page_records:
                last_ts = self._parse_timestamp(page_records[-1].get("time", ""))
                if last_ts and last_ts > period_end:
                    logger.debug(
                        "Son kayit (%s) period_end'i geciyor, pagination durduruluyor.",
                        last_ts,
                    )
                    break

            marker = new_marker

        return all_records

    # -----------------------------------------------------------------------
    # HTTP Istegi
    # -----------------------------------------------------------------------

    def _request_with_retry(self, marker: str | None) -> dict:
        """HTTP POST istegini yeniden deneme mekanizmasiyla gonderir."""
        payload = {
            "query": _EVENTS_FEED_QUERY,
            "variables": {
                "accountIDs": [self._account_id],
                "marker":     marker,
                "filters":    _EVENT_TYPE_FILTERS,
                "limit":      CATO_API_PAGE_SIZE,
            },
        }

        last_exc: Exception | None = None
        for attempt in range(1, CATO_API_MAX_RETRIES + 1):
            try:
                response = requests.post(
                    self._endpoint,
                    json=payload,
                    headers=self._headers,
                    timeout=CATO_API_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                data = response.json()

                if "errors" in data:
                    error_msgs = [e.get("message", str(e)) for e in data["errors"]]
                    raise CatoApiError(
                        f"GraphQL hatalari: {'; '.join(error_msgs)}"
                    )

                return data

            except requests.exceptions.Timeout as exc:
                last_exc = exc
                logger.warning(
                    "Deneme %d/%d: istek zaman asimina ugradi. Yeniden deneniyor...",
                    attempt, CATO_API_MAX_RETRIES,
                )
            except requests.exceptions.ConnectionError as exc:
                last_exc = exc
                logger.warning(
                    "Deneme %d/%d: baglanti hatasi. Yeniden deneniyor...",
                    attempt, CATO_API_MAX_RETRIES,
                )
            except requests.exceptions.HTTPError as exc:
                last_exc = exc
                if exc.response is not None and exc.response.status_code == 429:
                    wait = CATO_API_RETRY_DELAY_SECONDS * attempt
                    logger.warning("Rate limit (429). %ds bekleniyor...", wait)
                    time.sleep(wait)
                    continue
                raise CatoApiError(
                    f"HTTP {exc.response.status_code if exc.response else '?'} hatasi: {exc}"
                ) from exc
            except CatoApiError:
                raise

            if attempt < CATO_API_MAX_RETRIES:
                time.sleep(CATO_API_RETRY_DELAY_SECONDS)

        raise CatoApiError(
            f"API istegi {CATO_API_MAX_RETRIES} denemede de basarisiz oldu: {last_exc}"
        )

    # -----------------------------------------------------------------------
    # Normallestirme
    # -----------------------------------------------------------------------

    def _normalise(self, records: list[dict]) -> pd.DataFrame:
        """
        Cato API ham kayitlarini pipeline DataFrame formatina donusturur.

        Cato API iki yapi sunar:
          - fieldsMap: {alan_adi: [deger_listesi]} sozlugu
          - flatFields: [{fieldName, value}] listesi

        Her ikisini de dener; basarisiz alanlar icin diger yapiya fallback yapar.
        """
        rows: list[dict] = []

        for rec in records:
            flat: dict[str, str] = {}
            for field in rec.get("flatFields", []):
                name  = field.get("fieldName", "")
                value = field.get("value", "")
                if name:
                    flat[name] = value

            fields_map: dict[str, list] = rec.get("fieldsMap") or {}

            def _get(key: str) -> str:
                if key in flat:
                    return flat[key]
                vals = fields_map.get(key)
                if vals:
                    return str(vals[0]) if isinstance(vals, list) else str(vals)
                return ""

            timestamp_raw = rec.get("time") or _get("time") or _get("event_timestamp")
            site  = _get("src_site_name") or _get("site_name") or _get("site")
            event = _get("event_sub_type") or _get("event_name") or _get("action")
            iface = _get("socket_interface") or _get("interface")
            role  = _get("socket_role") or _get("role")

            ts = self._parse_timestamp(timestamp_raw)
            if ts is None:
                logger.debug("Gecersiz timestamp, kayit atlandi: %r", timestamp_raw)
                continue

            if not all([site, event, iface, role]):
                logger.debug(
                    "Eksik alan, kayit atlandi: site=%r event=%r iface=%r role=%r",
                    site, event, iface, role,
                )
                continue

            rows.append({
                COL_SITE:  site,
                COL_TIME:  ts,
                COL_EVENT: event,
                COL_IFACE: iface,
                COL_ROLE:  role,
            })

        if not rows:
            return self._empty_dataframe()

        df = pd.DataFrame(rows)
        logger.debug("Normallestirme tamamlandi: %d gecerli kayit.", len(df))
        return df

    # -----------------------------------------------------------------------
    # Yardimci Metotlar
    # -----------------------------------------------------------------------

    @staticmethod
    def _parse_timestamp(raw: str | None) -> datetime | None:
        """
        Cato API'sinin gonderebilecegi farkli timestamp formatlarini parse eder.
        Her zaman timezone-aware Europe/Istanbul olarak dondurur.

        Cato genellikle Unix ms timestamp veya ISO 8601 string gonderir.
        """
        if not raw:
            return None
        try:
            if isinstance(raw, (int, float)) or (isinstance(raw, str) and raw.isdigit()):
                ms = int(raw)
                if ms > 1e12:
                    ms = ms // 1000
                dt_utc = datetime.fromtimestamp(ms, tz=_UTC)
                return dt_utc.astimezone(TZ)

            if isinstance(raw, str):
                raw_clean = raw.replace("Z", "+00:00")
                dt = datetime.fromisoformat(raw_clean)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=_UTC)
                return dt.astimezone(TZ)

        except (ValueError, OSError, OverflowError):
            pass
        return None

    @staticmethod
    def _empty_dataframe() -> pd.DataFrame:
        """Sutun yapisi dogru ama bos bir DataFrame dondurur."""
        return pd.DataFrame(columns=[COL_SITE, COL_TIME, COL_EVENT, COL_IFACE, COL_ROLE])
