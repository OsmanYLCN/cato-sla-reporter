"""
main.py
=======
Cato SLA Reporter — CLI giriş noktası ve pipeline orkestratörü.

Kullanım:
    python main.py --input <CSV_YOLU> --period <1|3> [--mode <manual|auto>] [--output <KLASÖR>]

Örnekler:
    # Son 30 günü analiz et (Manuel Mod)
    python main.py --input sample_data/Cato_events_sample.csv --period 1

    # Son 90 günü analiz et, çıktıyı özel klasöre yaz
    python main.py --input sample_data/Cato_events_sample.csv --period 3 --output ./raporlar

    # Otomatik Mod: bir önceki tam ay (CronJob için)
    python main.py --input /data/cato_events.csv --period 1 --mode auto
"""

import argparse
import sys
import datetime as _dt
from datetime import date, datetime, timedelta, timezone
from calendar import monthrange
from zoneinfo import ZoneInfo

from config.settings import PERIOD_LABELS, TZ
from data_ingestion.csv_reader import CsvLogReader
from engine.leg_detector import detect_legs
from engine.sla_calculator import calculate_sla
from engine.state_machine import detect_outages
from preprocessing.transformer import transform
from reporting.excel_exporter import export_to_excel
from utils.logger import get_logger

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """
    Komut satırı argümanlarını ayrıştırır ve doğrular.

    Args:
        argv: Argüman listesi. None ise sys.argv[1:] kullanılır.

    Returns:
        Ayrıştırılmış argüman namespace'i.
    """
    parser = argparse.ArgumentParser(
        prog="cato-sla-reporter",
        description=(
            "Cato Networks cihaz loglarından lokasyon bazlı "
            "SLA / Availability raporu oluşturur."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Örnekler:\n"
            "  python main.py --input events.csv --period 1\n"
            "  python main.py --input events.csv --period 3 --output ./raporlar\n"
            "  python main.py --input events.csv --period 1 --mode auto\n"
        ),
    )

    parser.add_argument(
        "--input",
        metavar="CSV_YOLU",
        required=True,
        help="Cato Networks log CSV dosyasının yolu.",
    )
    parser.add_argument(
        "--period",
        type=int,
        choices=[1, 3],
        required=True,
        metavar="{1,3}",
        help="Rapor dönemi: 1 (Son 30 gün / Önceki Ay) veya 3 (Son 90 gün / Önceki Çeyrek).",
    )
    parser.add_argument(
        "--mode",
        choices=["manual", "auto"],
        default="manual",
        help=(
            "Çalışma modu. "
            "'manual': Geriye dönük son 30/90 gün. "
            "'auto': Bir önceki tam takvim ayı/çeyreği (CronJob için). "
            "(Varsayılan: manual)"
        ),
    )
    parser.add_argument(
        "--output",
        metavar="KLASÖR",
        default=None,
        help="Çıktı Excel dosyasının yazılacağı klasör. (Varsayılan: ./output)",
    )

    return parser.parse_args(argv)


def resolve_period_dates(
    period_months: int,
    mode: str,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """
    Çalışma moduna göre rapor döneminin başlangıç ve bitiş tarihlerini hesaplar.

    Manuel Mod:
        - 1 ay → Bugünden 30 gün öncesi (00:00:00) → Bugün (23:59:59)
        - 3 ay → Bugünden 90 gün öncesi (00:00:00) → Bugün (23:59:59)

    Otomatik Mod:
        - 1 ay → Önceki takvim ayının 1'i (00:00:00) → Sonu (23:59:59)
        - 3 ay → Önceki takvim çeyreğinin ilk günü → Sonu (23:59:59)

    Args:
        period_months: 1 veya 3.
        mode: "manual" veya "auto".
        now: Override için mevcut zaman (test amacıyla). None ise gerçek zaman.

    Returns:
        (period_start, period_end) — her ikisi de Europe/Istanbul timezone-aware.
    """

    now_local = now or datetime.now(tz=TZ)
    today = now_local.date()

    if mode == "manual":
        days_back = 30 * period_months  # 30 veya 90 gün
        start_date = today - timedelta(days=days_back)
        period_start = datetime(
            start_date.year, start_date.month, start_date.day,
            0, 0, 0, tzinfo=TZ,
        )
        period_end = datetime(
            today.year, today.month, today.day,
            23, 59, 59, tzinfo=TZ,
        )

    elif mode == "auto":
        if period_months == 1:
            # Önceki ay
            first_of_this_month = today.replace(day=1)
            last_month_end = first_of_this_month - timedelta(days=1)
            last_month_start = last_month_end.replace(day=1)
            _, last_day = monthrange(last_month_end.year, last_month_end.month)
            period_start = datetime(
                last_month_start.year, last_month_start.month, 1,
                0, 0, 0, tzinfo=TZ,
            )
            period_end = datetime(
                last_month_end.year, last_month_end.month, last_day,
                23, 59, 59, tzinfo=TZ,
            )

        else:  # period_months == 3
            # Önceki tam çeyrek
            current_quarter = (today.month - 1) // 3  # 0-3
            if current_quarter == 0:
                # Q4 of previous year
                q_start_month = 10
                q_end_month = 12
                q_year = today.year - 1
            else:
                q_start_month = (current_quarter - 1) * 3 + 1
                q_end_month = q_start_month + 2
                q_year = today.year
            _, last_day = monthrange(q_year, q_end_month)
            period_start = datetime(q_year, q_start_month, 1, 0, 0, 0, tzinfo=TZ)
            period_end = datetime(q_year, q_end_month, last_day, 23, 59, 59, tzinfo=TZ)

    else:
        raise ValueError(f"Geçersiz mod: '{mode}'. 'manual' veya 'auto' olmalı.")

    logger.info(
        "Rapor dönemi belirlendi [%s modu]: %s → %s",
        mode,
        period_start.strftime("%Y-%m-%d %H:%M:%S %Z"),
        period_end.strftime("%Y-%m-%d %H:%M:%S %Z"),
    )

    return period_start, period_end


def run(args: argparse.Namespace) -> None:
    """
    Ana pipeline'ı çalıştırır.

    Args:
        args: parse_args() çıktısı.
    """
    logger.info("=" * 60)
    logger.info("Cato SLA Reporter başlatıldı.")
    logger.info(
        "Parametreler: input='%s' | period=%d ay | mode=%s",
        args.input, args.period, args.mode,
    )
    logger.info("=" * 60)

    # -----------------------------------------------------------------------
    # Adım 1: Rapor dönemini belirle
    # -----------------------------------------------------------------------
    period_start, period_end = resolve_period_dates(
        period_months=args.period,
        mode=args.mode,
    )

    # -----------------------------------------------------------------------
    # Adım 2: CSV oku
    # -----------------------------------------------------------------------
    reader = CsvLogReader(args.input)
    raw_df = reader.read()

    if raw_df.empty:
        logger.error("Veri okunamadı veya CSV boş. İşlem durduruluyor.")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Adım 3: Dönüştür (UTC → Istanbul, temizleme, sıralama)
    # -----------------------------------------------------------------------
    clean_df = transform(raw_df)

    if clean_df.empty:
        logger.error(
            "Temizleme sonrası veri kalmadı. "
            "CSV formatını ve sütun adlarını kontrol edin."
        )
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Adım 4: Bacak haritasını oluştur
    # -----------------------------------------------------------------------
    leg_map = detect_legs(clean_df)

    if not leg_map:
        logger.error("Hiç site tespit edilemedi. İşlem durduruluyor.")
        sys.exit(1)

    all_sites = list(leg_map.keys())

    # -----------------------------------------------------------------------
    # Adım 5: Kesintileri tespit et (State Machine)
    # -----------------------------------------------------------------------
    outages = detect_outages(
        df=clean_df,
        leg_map=leg_map,
        period_start=period_start,
        period_end=period_end,
    )

    # -----------------------------------------------------------------------
    # Adım 6: SLA hesapla
    # -----------------------------------------------------------------------
    summary_df = calculate_sla(
        outages=outages,
        all_sites=all_sites,
        period_months=args.period,
    )

    # -----------------------------------------------------------------------
    # Adım 7: Excel'e yaz
    # -----------------------------------------------------------------------
    output_path = export_to_excel(
        summary_df=summary_df,
        outages=outages,
        period_months=args.period,
        output_dir=args.output,
        report_date=date.today(),
    )

    # -----------------------------------------------------------------------
    # Özet
    # -----------------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("İşlem tamamlandı.")
    logger.info("Rapor dönemi : %s", PERIOD_LABELS[args.period])
    logger.info("Toplam site  : %d", len(summary_df))
    logger.info(
        "Passed / Failed: %d / %d",
        (summary_df["SLA Durumu"] == "Passed").sum(),
        (summary_df["SLA Durumu"] == "Failed").sum(),
    )
    logger.info("Rapor dosyası: %s", output_path.resolve())
    logger.info("=" * 60)


def main() -> None:
    """Giriş noktası."""
    try:
        args = parse_args()
        run(args)
    except KeyboardInterrupt:
        logger.warning("İşlem kullanıcı tarafından iptal edildi.")
        sys.exit(0)
    except Exception as exc:
        logger.error("Beklenmedik hata: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
