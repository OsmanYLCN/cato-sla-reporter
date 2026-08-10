"""
utils/logger.py
===============
Merkezi logging yapılandırması.
Tüm modüller `get_logger(__name__)` çağrısı ile bu modülden logger alır.

Özellikler:
    - Konsol: INFO ve üzeri, renkli prefix
    - Dosya:  DEBUG ve üzeri, logs/ klasörüne tarih damgalı dosya
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

from config.settings import LOG_DIR, LOG_FORMAT, LOG_DATE_FORMAT, LOG_LEVEL

# ---------------------------------------------------------------------------
# ANSI Renk Kodları (Windows 10+ ve modern terminaller destekler)
# ---------------------------------------------------------------------------
_COLORS: dict[str, str] = {
    "DEBUG":    "\033[36m",   # Cyan
    "INFO":     "\033[32m",   # Yeşil
    "WARNING":  "\033[33m",   # Sarı
    "ERROR":    "\033[31m",   # Kırmızı
    "CRITICAL": "\033[35m",   # Mor
    "RESET":    "\033[0m",
}


class _ColoredFormatter(logging.Formatter):
    """Konsol çıktısı için ANSI renk kodları ekleyen formatter."""

    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelname, _COLORS["RESET"])
        reset = _COLORS["RESET"]
        record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)


def get_logger(name: str) -> logging.Logger:
    """
    İsme göre yapılandırılmış bir Logger döndürür.

    Args:
        name: Logger adı. Genellikle __name__ kullanılır.

    Returns:
        Yapılandırılmış logging.Logger örneği.
    """
    logger = logging.getLogger(name)

    # Aynı logger birden fazla kez yapılandırılmasın
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # -----------------------------------------------------------------------
    # Konsol Handler (INFO+)
    # -----------------------------------------------------------------------
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    # Windows cp1254 terminallerde UTF-8 semboller bozulmasın
    if hasattr(console_handler.stream, 'reconfigure'):
        try:
            console_handler.stream.reconfigure(encoding='utf-8')
        except Exception:
            pass
    console_handler.setFormatter(
        _ColoredFormatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    )
    logger.addHandler(console_handler)

    # -----------------------------------------------------------------------
    # Dosya Handler (DEBUG+)
    # -----------------------------------------------------------------------
    try:
        log_dir = Path(LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_filename = log_dir / f"cato_sla_{datetime.now().strftime('%Y%m%d')}.log"

        file_handler = logging.FileHandler(log_filename, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
        )
        logger.addHandler(file_handler)
    except OSError as exc:
        logger.warning("Log dosyası oluşturulamadı: %s", exc)

    # Root logger'a yayılmayı kapat
    logger.propagate = False

    return logger
