from zoneinfo import ZoneInfo

# Genel sistem parametreleri ve saat dilimi
TIMEZONE: str = "Europe/Istanbul"
TZ: ZoneInfo = ZoneInfo(TIMEZONE)

# SLA hedef eşiği (%)
SLA_THRESHOLD_PCT: float = 99.90

# Rapor dönemlerinin toplam dakika karşılıkları
PERIOD_MINUTES: dict[int, int] = {
    1: 43_200,   # 30 gün
    3: 129_600,  # 90 gün
}

PERIOD_LABELS: dict[int, str] = {
    1: "Son 1 Ay",
    3: "Son 3 Ay",
}

# Anlık bağlantı dalgalanmalarını tolere etme süresi (saniye)
CORRELATION_WINDOW_SECONDS: int = 30

# Log veri yapısı ve sütun eşlemeleri
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

VALID_EVENT_TYPES: set[str] = {"Connected", "Disconnected"}

# Dosya ve dizin yolları
OUTPUT_DIR: str = "output"
LOG_DIR: str = "logs"

# Excel çıktı biçimlendirme ayarları
EXCEL_SHEET_SUMMARY: str = "SLA Özet"
EXCEL_SHEET_DETAILS: str = "Kesinti Detayları"

COLOR_PASSED_BG: str = "FF92D050"
COLOR_PASSED_FONT: str = "FF375623"
COLOR_FAILED_BG: str = "FFFF0000"
COLOR_FAILED_FONT: str = "FF7B0000"
COLOR_HEADER_BG: str = "FF203864"
COLOR_HEADER_FONT: str = "FFFFFFFF"
COLOR_ROW_ALT: str = "FFD9E1F2"

# Log yapılandırması
LOG_LEVEL: str = "DEBUG"
LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
