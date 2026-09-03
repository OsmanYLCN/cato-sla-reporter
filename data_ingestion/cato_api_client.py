"""
data_ingestion/cato_api_client.py

Cato Networks GraphQL API istemcisi.

Belirtilen zaman araligindaki connectivity event'lerini 'events' query'si
ile tarih bazli ceker, mevcut pipeline'in bekledigi DataFrame formatina
donusturur.

NOT: Cato'nun 'eventsFeed' API'si sadece canli (live) kuyruk akisi icin
tasarlanmistir ve gecmis verilere tarih filtrelemesi desteklemiyor.
Bunun yerine, gecmise donuk tarih aralikli sorgulama icin 'events' query'si
kullanilir; bu sorgu 'timeFrame' parametresiyle belirli bir araligi destekler.
"""
import math
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
# GraphQL Sorgu Sabiti — events (tarih aralikli, historik veri)
# ---------------------------------------------------------------------------
_EVENTS_QUERY = """
query GetConnectivityEvents(
  $accountID:  ID!
  $timeFrame:  TimeFrame!
  $filters:    [EventsFilter!]
  $dimensions: [EventsDimension]
  $measures:   [EventsMeasure]
) {
  events(
    accountID:  $accountID
    timeFrame:  $timeFrame
    filters:    $filters
    dimensions: $dimensions
    measures:   $measures
  ) {
    records {
      flatFields
      fieldsMap
    }
  }
}
"""

# Zorunlu boyutlar (istenen alanlar) ve olcum
_DIMENSIONS = [
    {"fieldName": "event_sub_type"},
    {"fieldName": "src_site_name"},
    {"fieldName": "socket_interface"},
    {"fieldName": "socket_role"},
    {"fieldName": "time"},
]

_MEASURES = [
    {"fieldName": "event_count", "aggType": "count"}
]

_FILTERS = [
    {"fieldName": "event_type", "operator": "is", "values": ["Connectivity"]}
]


class CatoApiError(Exception):
    """Cato API'sinden donen hata durumlarini temsil eder."""


class CatoApiClient:
    """
    Cato Networks GraphQL API istemcisi.

    'events' query'si ile belirtilen tarih araligindaki connectivity
    event loglarini ceker ve pipeline'a uygun DataFrame olarak dondurur.

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

        Cato 'events' query'si UTC formatli tarih araligini destekler:
          utc.YYYY-MM-{DD/HH:MM:SS--DD/HH:MM:SS}

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

        time_frame = self._build_timeframe(period_start, period_end)
        logger.info("Kullanilan timeFrame: %s", time_frame)

        raw_records = self._fetch_all(time_frame)

        if not raw_records:
            logger.warning("API'den hic event kaydi donmedi.")
            return self._empty_dataframe()

        df = self._normalise(raw_records)

        # Zaman araligini istemci tarafinda filtrele (hassasiyet icin)
        before_filter = len(df)
        mask = (df[COL_TIME] >= period_start) & (df[COL_TIME] <= period_end)
        df = df[mask].reset_index(drop=True)
        filtered_out = before_filter - len(df)

        if filtered_out > 0:
            logger.debug("%d kayit zaman aralik filtresi sonrasi elendi.", filtered_out)

        logger.info(
            "API'den %d ham kayit alindi, zaman filtresinden sonra %d kayit isleme alinacak.",
            before_filter,
            len(df),
        )
        return df

    # -----------------------------------------------------------------------
    # TimeFrame Olusturma
    # -----------------------------------------------------------------------

    @staticmethod
    def _build_timeframe(period_start: datetime, period_end: datetime) -> str:
        """
        Cato API'sinin kabul ettigi UTC tarih aralikli timeFrame stringini olusturur.

        Cato, tek ay icin ozel bir format ister:
          utc.YYYY-MM-{DD/HH:MM:SS--DD/HH:MM:SS}  (ay yil prefix ile)

        Birden fazla ay icin ise:
          utc.YYYY-MM-DD/HH:MM:SS--YYYY-MM-DD/HH:MM:SS  formatini dener;
          API kabul etmezse last.PxD fallback kullanilir.

        NOT: UTC donusumu yapilir cunku Cato API UTC beklentisindedir.
        """
        start_utc = period_start.astimezone(ZoneInfo("UTC"))
        end_utc   = period_end.astimezone(ZoneInfo("UTC"))

        if start_utc.year == end_utc.year and start_utc.month == end_utc.month:
            # Ayni takvim ayindaki aralik — tek parca, Cato'nun ozel formati
            return (
                f"utc.{start_utc.year}-{start_utc.month:02d}-"
                f"{{{start_utc.day:02d}/{start_utc.hour:02d}:{start_utc.minute:02d}:{start_utc.second:02d}"
                f"--"
                f"{end_utc.day:02d}/{end_utc.hour:02d}:{end_utc.minute:02d}:{end_utc.second:02d}}}"
            )
        else:
            # Birden fazla takvim ayini kapsayan aralik
            # Cato'nun "last.PxD" formatini kullan — bugunun geri sayimina gore calisir.
            # Bu nedenle period_end'i bugun gibi kabul ederek gun sayisi hesaplanir.
            from datetime import timezone
            now_utc = datetime.now(tz=timezone.utc)
            days = (now_utc.date() - start_utc.date()).days
            if days < 1:
                days = 1
            return f"last.P{days}D"

    # -----------------------------------------------------------------------
    # Veri Cekme
    # -----------------------------------------------------------------------

    def _fetch_all(self, time_frame: str) -> list[dict]:
        """API'den tum kayitlari ceker."""
        payload = {
            "query": _EVENTS_QUERY,
            "variables": {
                "accountID":  self._account_id,
                "timeFrame":  time_frame,
                "filters":    _FILTERS,
                "dimensions": _DIMENSIONS,
                "measures":   _MEASURES,
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

                records = (
                    data.get("data", {})
                        .get("events", {})
                        .get("records", [])
                )
                logger.info("API'den %d kayit alindi.", len(records))
                return records

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

        events query'si fieldsMap ve flatFields (list of lists) olarak
        iki format dondurur. Her ikisini de destekler.
        """
        rows: list[dict] = []

        for rec in records:
            # fieldsMap tercihli yol (events query'si genellikle bunu dolu dondurur)
            fields_map: dict = rec.get("fieldsMap") or {}

            # flatFields fallback (list of [name, value] pairs)
            flat: dict[str, str] = {}
            for field in rec.get("flatFields", []):
                if isinstance(field, list) and len(field) >= 2:
                    name = str(field[0])
                    value = str(field[1]) if field[1] is not None else ""
                    if name:
                        flat[name] = value

            def _get(key: str) -> str:
                if key in fields_map:
                    val = fields_map[key]
                    if isinstance(val, list):
                        return str(val[0]) if val else ""
                    return str(val) if val is not None else ""
                return flat.get(key, "")

            timestamp_raw = _get("time") or _get("event_timestamp")
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
