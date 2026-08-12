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
    """Ham log verisini temizler, UTC zaman bilgisini Europe/Istanbul saat dilimine cevirir."""
    logger.info("Veri donusumu basliyor. Girdi satir sayisi: %d", len(df))

    if df.empty:
        logger.warning("Bos DataFrame alindi; donusum atlaniyor.")
        return df

    df = df.copy()

    # String alanları temizle
    for col in [COL_SITE, COL_EVENT, COL_IFACE, COL_ROLE]:
        if col in df.columns:
            df[col] = df[col].str.strip()

    logger.debug("String normalizasyonu tamamlandi.")

    # UTC zaman verisini parse et
    try:
        df[COL_TIME] = pd.to_datetime(df[COL_TIME], utc=True, errors="coerce")
    except Exception as exc:
        raise ValueError(
            f"`{COL_TIME}` sutunu datetime formatina donusturulemedi: {exc}"
        ) from exc

    invalid_time_count = df[COL_TIME].isna().sum()
    if invalid_time_count > 0:
        logger.warning(
            "%d satir gecersiz zaman damgasi nedeniyle atiliyor.", invalid_time_count
        )
        df = df.dropna(subset=[COL_TIME])

    logger.debug("UTC datetime donusumu tamamlandi.")

    # Saat dilimini dönüştür (UTC -> Europe/Istanbul)
    df[COL_TIME] = df[COL_TIME].dt.tz_convert(_TZ)
    logger.debug("Saat dilimi donusumu tamamlandi: UTC → %s", TIMEZONE)

    # Eksik veya geçersiz verileri temizle
    critical_cols = [COL_SITE, COL_EVENT, COL_IFACE, COL_ROLE]
    before_null_drop = len(df)
    df = df.dropna(subset=critical_cols)
    null_dropped = before_null_drop - len(df)
    if null_dropped > 0:
        logger.warning(
            "%d satir kritik sutunlardaki null deger nedeniyle atildi.", null_dropped
        )

    for col in critical_cols:
        empty_mask = df[col] == ""
        empty_count = empty_mask.sum()
        if empty_count > 0:
            logger.warning(
                "'%s' sutununda %d bos string degeri atiliyor.", col, empty_count
            )
            df = df[~empty_mask]

    # Tekrarlayan verileri kaldır ve kronolojik sırala
    before_dedup = len(df)
    df = df.drop_duplicates()
    dedup_count = before_dedup - len(df)
    if dedup_count > 0:
        logger.debug("%d duplicate satir kaldirildi.", dedup_count)

    df = df.sort_values(by=COL_TIME, ascending=True).reset_index(drop=True)

    logger.info(
        "Donusum tamamlandi. Cikti satir sayisi: %d (atilan: %d).",
        len(df),
        invalid_time_count + (before_null_drop - len(df)),
    )

    return df
