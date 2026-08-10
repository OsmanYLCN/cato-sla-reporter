"""
engine/leg_detector.py
=======================
Her site için benzersiz bacak (leg) kümesini dinamik olarak tespit eden modül.

Bacak: (socket_interface, socket_role) ikilisi.
Örn: ("WAN1", "primary"), ("WAN2", "secondary"), ("PRIMARY1", "primary")

Tek bacaklı siteler de doğru şekilde tespit edilir (küme boyutu = 1).
"""

import pandas as pd

from config.settings import COL_IFACE, COL_ROLE, COL_SITE
from utils.logger import get_logger

logger = get_logger(__name__)

# Tip takma adı: Site adından bacak kümesine eşleme
LegMap = dict[str, frozenset[tuple[str, str]]]


def detect_legs(df: pd.DataFrame) -> LegMap:
    """
    DataFrame içindeki her site için benzersiz bacak kümesini tespit eder.

    Her bacak; (socket_interface, socket_role) çiftidir.
    Küme, o site için rapor dönemi boyunca gözlemlenen tüm bacakları içerir.

    Args:
        df: Transformer'dan geçirilmiş, temizlenmiş log DataFrame'i.

    Returns:
        Site adından frozenset bacak kümesine eşleyen sözlük.
        Örnek:
        {
            "Istanbul-HQ": frozenset({("WAN1","primary"), ("WAN2","secondary")}),
            "Ankara-DC":   frozenset({("PRIMARY1","primary")}),
        }

    Raises:
        ValueError: DataFrame boşsa veya gerekli sütunlar eksikse.
    """
    if df.empty:
        logger.warning("Boş DataFrame alındı; bacak tespiti yapılamıyor.")
        return {}

    required = {COL_SITE, COL_IFACE, COL_ROLE}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Bacak tespiti için gerekli sütunlar eksik: {missing}")

    leg_map: LegMap = {}

    for site, group in df.groupby(COL_SITE, sort=False):
        # Benzersiz (interface, role) çiftlerini topla
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
        "%d site için bacak haritası oluşturuldu. "
        "(Tek bacaklı: %d, Çok bacaklı: %d)",
        len(leg_map),
        sum(1 for legs in leg_map.values() if len(legs) == 1),
        sum(1 for legs in leg_map.values() if len(legs) > 1),
    )

    return leg_map
