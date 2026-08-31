import logging
import sys
from datetime import datetime
from pathlib import Path

from config.settings import LOG_DIR, LOG_FORMAT, LOG_DATE_FORMAT, LOG_LEVEL

# Konsol log çıktıları için renk tanımları
_COLORS: dict[str, str] = {
    "DEBUG":    "\033[36m",
    "INFO":     "\033[32m",
    "WARNING":  "\033[33m",
    "ERROR":    "\033[31m",
    "CRITICAL": "\033[35m",
    "RESET":    "\033[0m",
}


class _ColoredFormatter(logging.Formatter):
    """Konsol log seviyelerini renklendirir."""

    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelname, _COLORS["RESET"])
        reset = _COLORS["RESET"]
        record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)


_shared_file_handler: logging.FileHandler | None = None


def _get_file_handler() -> logging.FileHandler | None:
    """Tum modul logger'lari icin ortak paylasilan tekil dosya isleyicisini dondurur."""
    global _shared_file_handler
    if _shared_file_handler is not None:
        return _shared_file_handler

    try:
        log_dir = Path(LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_filename = log_dir / f"cato_sla_{datetime.now().strftime('%Y%m%d')}.log"

        _shared_file_handler = logging.FileHandler(log_filename, encoding="utf-8")
        _shared_file_handler.setLevel(logging.DEBUG)
        _shared_file_handler.setFormatter(
            logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
        )
        return _shared_file_handler
    except OSError as exc:
        logging.getLogger(__name__).warning("Log dosyasi olusturulamadi: %s", exc)
        return None


def get_logger(name: str) -> logging.Logger:
    """Modul bazli konsol ve dosya logger'i olusturur."""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, LOG_LEVEL, logging.DEBUG))

    # Konsol ciktisi yapilandirmasi
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    if hasattr(console_handler.stream, 'reconfigure'):
        try:
            console_handler.stream.reconfigure(encoding='utf-8')
        except Exception:
            pass
    console_handler.setFormatter(
        _ColoredFormatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    )
    logger.addHandler(console_handler)

    # Gunluk log dosyasi yapilandirmasi (ortak dosya isleyicisi)
    file_handler = _get_file_handler()
    if file_handler and file_handler not in logger.handlers:
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger

