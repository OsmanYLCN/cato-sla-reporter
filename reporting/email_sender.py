"""
reporting/email_sender.py
==========================
SMTP ile e-posta gönderimi — ilerideki Otomatik Mod için stub.

Bu modül şu an NotImplementedError fırlatır.
İleride SMTP yapılandırması, alıcı listesi ve .xlsx ek gönderimi
bu modüle eklenerek implement edilecektir.
"""

from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)


class EmailSender:
    """
    SLA raporu Excel dosyasını SMTP ile gönderen sınıf.

    Args:
        smtp_host: SMTP sunucu adresi.
        smtp_port: SMTP port numarası.
        username: Gönderici e-posta adresi.
        password: SMTP şifre veya uygulama anahtarı.
        recipients: Alıcı e-posta adreslerinin listesi.

    Note:
        Bu sınıf henüz implement edilmemiştir.
    """

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
        """
        Rapor dosyasını e-posta ile gönderir.

        Args:
            report_path: Gönderilecek .xlsx dosyasının yolu.
            subject: E-posta konusu. None ise otomatik oluşturulur.

        Raises:
            NotImplementedError: Bu metot henüz implement edilmemiştir.
        """
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
