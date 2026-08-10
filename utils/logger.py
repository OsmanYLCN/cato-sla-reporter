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


def get_logger(name: str) -> logging.Logger:
    """Modül bazlı konsol ve dosya logger'ı oluşturur."""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Konsol çıktısı yapılandırması
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

    # Günlük log dosyası yapılandırması
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

    logger.propagate = False
    return logger
