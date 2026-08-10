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
    """Ham log verisini temizler, UTC zaman bilgisini Europe/Istanbul saat dilimine çevirir."""
    logger.info("Veri dönüşümü başlıyor. Girdi satır sayısı: %d", len(df))

    if df.empty:
        logger.warning("Boş DataFrame alındı; dönüşüm atlanıyor.")
        return df

    df = df.copy()

    # String alanları temizle
    for col in [COL_SITE, COL_EVENT, COL_IFACE, COL_ROLE]:
        if col in df.columns:
            df[col] = df[col].str.strip()

    logger.debug("String normalizasyonu tamamlandı.")

    # UTC zaman verisini parse et
    try:
        df[COL_TIME] = pd.to_datetime(df[COL_TIME], utc=True, errors="coerce")
    except Exception as exc:
        raise ValueError(
            f"`{COL_TIME}` sütunu datetime formatına dönüştürülemedi: {exc}"
        ) from exc

    invalid_time_count = df[COL_TIME].isna().sum()
    if invalid_time_count > 0:
        logger.warning(
            "%d satır geçersiz zaman damgası nedeniyle atılıyor.", invalid_time_count
        )
        df = df.dropna(subset=[COL_TIME])

    logger.debug("UTC datetime dönüşümü tamamlandı.")

    # Saat dilimini dönüştür (UTC -> Europe/Istanbul)
    df[COL_TIME] = df[COL_TIME].dt.tz_convert(_TZ)
    logger.debug("Saat dilimi dönüşümü tamamlandı: UTC → %s", TIMEZONE)

    # Eksik veya geçersiz verileri temizle
    critical_cols = [COL_SITE, COL_EVENT, COL_IFACE, COL_ROLE]
    before_null_drop = len(df)
    df = df.dropna(subset=critical_cols)
    null_dropped = before_null_drop - len(df)
    if null_dropped > 0:
        logger.warning(
            "%d satır kritik sütunlardaki null değer nedeniyle atıldı.", null_dropped
        )

    for col in critical_cols:
        empty_mask = df[col] == ""
        empty_count = empty_mask.sum()
        if empty_count > 0:
            logger.warning(
                "'%s' sütununda %d boş string değeri atılıyor.", col, empty_count
            )
            df = df[~empty_mask]

    # Tekrarlayan verileri kaldır ve kronolojik sırala
    before_dedup = len(df)
    df = df.drop_duplicates()
    dedup_count = before_dedup - len(df)
    if dedup_count > 0:
        logger.debug("%d duplicate satır kaldırıldı.", dedup_count)

    df = df.sort_values(by=COL_TIME, ascending=True).reset_index(drop=True)

    logger.info(
        "Dönüşüm tamamlandı. Çıktı satır sayısı: %d (atılan: %d).",
        len(df),
        before_null_drop - len(df) + invalid_time_count + null_dropped,
    )

    return df
