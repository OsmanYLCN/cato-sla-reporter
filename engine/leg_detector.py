import pytest as pt
import pandas as pd

from config.settings import COL_IFACE, COL_ROLE, COL_SITE
from utils.logger import get_logger

logger = get_logger(__name__)

LegMap = dict[str, frozenset[tuple[str, str]]]


def detect_legs(df: pd.DataFrame) -> LegMap:
    """Log kayitlarindan her siteye ait benzersiz bacak (interface + role) kumesini tespit eder."""
    if df.empty:
        logger.warning("Bos DataFrame alindi; bacak tespiti yapilamiyor.")
        return {}

    required = {COL_SITE, COL_IFACE, COL_ROLE}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Bacak tespiti icin gerekli sutunlar eksik: {missing}")

    leg_map: LegMap = {}

    for site, group in df.groupby(COL_SITE, sort=False):
        legs: frozenset[tuple[str, str]] = frozenset(
            zip(group[COL_IFACE], group[COL_ROLE])
        )
        leg_map[str(site)] = legs

        logger.debug(
            "Site '%s' → %d bacak tespit edildi: %s",
            site,
            len(legs),
            sorted(legs),
        )

    logger.info(
        "%d site için bacak haritasi olusturuldu. "
        "(Tek bacakli: %d, Cok bacakli: %d)",
        len(leg_map),
        sum(1 for legs in leg_map.values() if len(legs) == 1),
        sum(1 for legs in leg_map.values() if len(legs) > 1),
    )

    return leg_map
