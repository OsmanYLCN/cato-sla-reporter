from pathlib import Path

import pandas as pd

from config.settings import (
    REQUIRED_COLUMNS,
    COL_EVENT,
    VALID_EVENT_TYPES,
)
from data_ingestion.base_reader import BaseLogReader
from utils.logger import get_logger

logger = get_logger(__name__)

# Cato Networks CSV log okuyucusu
class CsvLogReader(BaseLogReader):
    """Cato Networks CSV log okuyucusu."""

    def __init__(self, file_path: str | Path) -> None:
        self._path = Path(file_path)

    def read(self) -> pd.DataFrame:
        """CSV dosyasını doğrular, geçerli log kayıtlarını DataFrame olarak döndürür."""
        logger.info("CSV okunuyor: %s", self._path)

        # Dosya varlık kontrolü
        if not self._path.exists():
            raise FileNotFoundError(
                f"CSV dosyası bulunamadı: '{self._path}'. "
                "Lütfen --input parametresini kontrol edin."
            )

        if not self._path.is_file():
            raise ValueError(f"Belirtilen yol bir dosya değil: '{self._path}'")

        try:
            df = pd.read_csv(
                self._path,
                low_memory=False,
                dtype=str,
            )
        except Exception as exc:
            raise RuntimeError(
                f"CSV okunurken hata oluştu: {exc}"
            ) from exc

        logger.debug("Okunan satır sayısı: %d", len(df))

        if df.empty:
            logger.warning("CSV dosyası boş veya yalnızca başlık satırı içeriyor.")
            return df

        # Sütun isimlerini ve zorunlu alanları doğrula
        df.columns = df.columns.str.strip()

        missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing_cols:
            raise ValueError(
                f"CSV'de zorunlu sütunlar eksik: {missing_cols}. "
                f"Mevcut sütunlar: {df.columns.tolist()}"
            )

        df = df[REQUIRED_COLUMNS].copy()

        # Geçersiz olay tiplerini ayıkla
        original_count = len(df)
        unexpected_mask = ~df[COL_EVENT].str.strip().isin(VALID_EVENT_TYPES)
        unexpected_count = unexpected_mask.sum()

        if unexpected_count > 0:
            unexpected_values = df.loc[unexpected_mask, COL_EVENT].unique().tolist()
            logger.warning(
                "%d satır geçersiz event_sub_type değeri nedeniyle atlanıyor: %s",
                unexpected_count,
                unexpected_values,
            )
            df = df[~unexpected_mask].copy()

        logger.info(
            "CSV yüklendi: %d satır (%d geçersiz kayıt atlandı).",
            len(df),
            original_count - len(df),
        )

        return df

    def __repr__(self) -> str:
        return f"<CsvLogReader path='{self._path}'>"
