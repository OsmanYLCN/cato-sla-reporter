"""
preprocessing/transformer.py
=============================
Ham DataFrame'i analiz motoruna hazır hale getiren dönüştürücü modül.

Sorumluluklar:
    1. `time` sütununu UTC datetime'a parse etmek
    2. UTC zamanını Europe/Istanbul (UTC+3) saat dilimine dönüştürmek
    3. String sütunlarını normalize etmek (strip, case)
    4. Null/boş değerleri filtrelemek
    5. Duplicate kayıtları temizlemek
    6. DataFrame'i zaman sırasına göre sıralamak
"""

from zoneinfo import ZoneInfo

import pandas as pd

from config.settings import (
    COL_EVENT,
    COL_IFACE,
    COL_ROLE,
    COL_SITE,
    COL_TIME,
    TIMEZONE,
)
from utils.logger import get_logger

logger = get_logger(__name__)

_UTC = ZoneInfo("UTC")
_TZ = ZoneInfo(TIMEZONE)


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ham log DataFrame'ini analiz için temizler ve dönüştürür.

    Adımlar:
        1. Boş DataFrame erken döndürülür.
        2. String sütunları strip ile normalize edilir.
        3. `time` sütunu UTC-aware datetime'a çevrilir.
        4. UTC datetime Europe/Istanbul saat dilimine dönüştürülür.
        5. Kritik sütunlarda null olan satırlar kaldırılır.
        6. Tam duplicate satırlar kaldırılır.
        7. Zaman sırasına göre ascending sıralanır.

    Args:
        df: CsvLogReader veya GraphQLLogReader'dan gelen ham DataFrame.

    Returns:
        Temizlenmiş, timezone-aware zaman damgalarına sahip pd.DataFrame.

    Raises:
        ValueError: `time` sütunu parse edilemiyorsa.
    """
    logger.info("Veri dönüşümü başlıyor. Girdi satır sayısı: %d", len(df))

    if df.empty:
        logger.warning("Boş DataFrame alındı; dönüşüm atlanıyor.")
        return df

    df = df.copy()

    # -------------------------------------------------------------------------
    # Adım 1: String sütunlarını normalize et
    # -------------------------------------------------------------------------
    for col in [COL_SITE, COL_EVENT, COL_IFACE, COL_ROLE]:
        if col in df.columns:
            df[col] = df[col].str.strip()

    logger.debug("String normalizasyonu tamamlandı.")

    # -------------------------------------------------------------------------
    # Adım 2: `time` sütununu UTC-aware datetime'a çevir
    # -------------------------------------------------------------------------
    try:
        # CSV'deki time değerleri UTC'dir; önce UTC-aware olarak parse et
        df[COL_TIME] = pd.to_datetime(df[COL_TIME], utc=True, errors="coerce")
    except Exception as exc:
        raise ValueError(
            f"`{COL_TIME}` sütunu datetime formatına dönüştürülemedi: {exc}"
        ) from exc

    # Parse edilemeyen zaman damgalarını raporla ve filtrele
    invalid_time_count = df[COL_TIME].isna().sum()
    if invalid_time_count > 0:
        logger.warning(
            "%d satır geçersiz zaman damgası nedeniyle atılıyor.", invalid_time_count
        )
        df = df.dropna(subset=[COL_TIME])

    logger.debug("UTC datetime dönüşümü tamamlandı.")

    # -------------------------------------------------------------------------
    # Adım 3: UTC → Europe/Istanbul dönüşümü
    # -------------------------------------------------------------------------
    df[COL_TIME] = df[COL_TIME].dt.tz_convert(_TZ)
    logger.debug("Saat dilimi dönüşümü tamamlandı: UTC → %s", TIMEZONE)

    # -------------------------------------------------------------------------
    # Adım 4: Kritik sütunlarda null kontrolü
    # -------------------------------------------------------------------------
    critical_cols = [COL_SITE, COL_EVENT, COL_IFACE, COL_ROLE]
    before_null_drop = len(df)
    df = df.dropna(subset=critical_cols)
    null_dropped = before_null_drop - len(df)
    if null_dropped > 0:
        logger.warning(
            "%d satır kritik sütunlardaki null değer nedeniyle atıldı.", null_dropped
        )

    # Boş string kontrolü
    for col in critical_cols:
        empty_mask = df[col] == ""
        empty_count = empty_mask.sum()
        if empty_count > 0:
            logger.warning(
                "'%s' sütununda %d boş string değeri atılıyor.", col, empty_count
            )
            df = df[~empty_mask]

    # -------------------------------------------------------------------------
    # Adım 5: Tam duplicate satırları kaldır
    # -------------------------------------------------------------------------
    before_dedup = len(df)
    df = df.drop_duplicates()
    dedup_count = before_dedup - len(df)
    if dedup_count > 0:
        logger.debug("%d duplicate satır kaldırıldı.", dedup_count)

    # -------------------------------------------------------------------------
    # Adım 6: Zaman sırasına göre sırala
    # -------------------------------------------------------------------------
    df = df.sort_values(by=COL_TIME, ascending=True).reset_index(drop=True)

    logger.info(
        "Dönüşüm tamamlandı. Çıktı satır sayısı: %d (atılan: %d).",
        len(df),
        before_null_drop - len(df) + invalid_time_count + null_dropped,
    )

    return df
