from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)

# E-posta gönderim istemcisi
class EmailSender:
    """E-posta rapor gönderimi için istemci sınıfı (ilerideki otomatik mod için taslak)."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        recipients: list[str],
    ) -> None:
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._username = username
        self._password = password
        self._recipients = recipients

    def send(self, report_path: Path, subject: str | None = None) -> None:
        """SMTP entegrasyonu henüz tamamlanmadığı için hata fırlatır."""
        logger.error(
            "EmailSender henüz implement edilmemiştir. "
            "E-posta gönderimi atlanıyor."
        )
        raise NotImplementedError(
            "SMTP e-posta gönderimi henüz geliştirilme aşamasındadır. "
            "Lütfen manuel modda çalışarak raporu --output ile kaydedin."
        )

    def __repr__(self) -> str:
        return (
            f"<EmailSender host='{self._smtp_host}:{self._smtp_port}' "
            f"recipients={self._recipients}>"
        )
