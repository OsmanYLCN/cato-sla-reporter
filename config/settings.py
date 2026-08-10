"""
config/settings.py
==================
Merkezi yapılandırma modülü.
Tüm sabitler, eşik değerleri ve proje genelindeki parametreler burada yönetilir.
Herhangi bir değeri değiştirmek için yalnızca bu dosyayı düzenlemek yeterlidir.
"""

from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Zaman Dilimi
# ---------------------------------------------------------------------------
TIMEZONE: str = "Europe/Istanbul"
TZ: ZoneInfo = ZoneInfo(TIMEZONE)

# ---------------------------------------------------------------------------
# SLA Eşik Değeri
# ---------------------------------------------------------------------------
SLA_THRESHOLD_PCT: float = 99.90  # Availability bu değerin altına düşerse Failed

# ---------------------------------------------------------------------------
# Rapor Dönemi Sabit Dakika Değerleri
# ---------------------------------------------------------------------------
# Müdür talebi: sabit dakika kullanılacak (takvim farkı hesaba katılmaz)
PERIOD_MINUTES: dict[int, int] = {
    1: 43_200,   # 30 gün × 24 saat × 60 dakika
    3: 129_600,  # 90 gün × 24 saat × 60 dakika
}

# Dönem etiketleri (Excel ve rapor başlıklarında görünür)
PERIOD_LABELS: dict[int, str] = {
    1: "Son 1 Ay",
    3: "Son 3 Ay",
}

# ---------------------------------------------------------------------------
# Korelasyon / Zaman Penceresi
# ---------------------------------------------------------------------------
CORRELATION_WINDOW_SECONDS: int = 30  # Bacaklar arası saniyelik tolerans

# ---------------------------------------------------------------------------
# CSV Sütun Tanımları
# ---------------------------------------------------------------------------
REQUIRED_COLUMNS: list[str] = [
    "src_site_name",
    "time",
    "event_sub_type",
    "socket_interface",
    "socket_role",
]

COL_SITE: str = "src_site_name"
COL_TIME: str = "time"
COL_EVENT: str = "event_sub_type"
COL_IFACE: str = "socket_interface"
COL_ROLE: str = "socket_role"

# Geçerli olay tipleri
VALID_EVENT_TYPES: set[str] = {"Connected", "Disconnected"}

# ---------------------------------------------------------------------------
# Çıktı Dizinleri
# ---------------------------------------------------------------------------
OUTPUT_DIR: str = "output"
LOG_DIR: str = "logs"

# ---------------------------------------------------------------------------
# Excel Biçimlendirme
# ---------------------------------------------------------------------------
EXCEL_SHEET_SUMMARY: str = "SLA Özet"
EXCEL_SHEET_DETAILS: str = "Kesinti Detayları"

# Conditional formatting renkleri (ARGB hex, openpyxl formatı)
COLOR_PASSED_BG: str = "FF92D050"   # Yeşil
COLOR_PASSED_FONT: str = "FF375623" # Koyu yeşil yazı
COLOR_FAILED_BG: str = "FFFF0000"   # Kırmızı
COLOR_FAILED_FONT: str = "FF7B0000" # Koyu kırmızı yazı
COLOR_HEADER_BG: str = "FF203864"   # Koyu lacivert başlık
COLOR_HEADER_FONT: str = "FFFFFFFF" # Beyaz başlık yazısı
COLOR_ROW_ALT: str = "FFD9E1F2"    # Alternatif satır arka planı (açık mavi)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL: str = "DEBUG"
LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
