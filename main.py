import argparse
import sys
from datetime import date, datetime, timedelta

from config.settings import (
    COL_TIME,
    PERIOD_LABELS,
    SLA_STATUS_FAILED,
    SLA_STATUS_PASSED,
    TZ,
)
from data_ingestion.csv_reader import CsvLogReader
from engine.leg_detector import detect_legs
from engine.sla_calculator import calculate_sla
from engine.state_machine import detect_outages
from preprocessing.transformer import transform
from reporting.excel_exporter import export_to_excel
from utils.logger import get_logger

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="cato-sla-reporter",
        description=(
            "Generate location-based SLA / Availability reports "
            "from Cato Networks device logs."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py --input events.csv --period 1\n"
            "  python main.py --input events.csv --period 3 --output ./reports\n"
            "  python main.py --input events.csv --period 1 --mode auto\n"
            "  python main.py --input events.csv --period 3 --mode auto\n"
        ),
    )

    parser.add_argument(
        "--input",
        metavar="CSV_PATH",
        required=True,
        help="Path to Cato Networks log CSV file.",
    )
    parser.add_argument(
        "--period",
        type=int,
        choices=[1, 3],
        required=True,
        metavar="{1,3}",
        help="Report period in months: 1 (Last 30 Days / Last 1 Month) or 3 (Last 90 Days / Last 3 Months).",
    )
    parser.add_argument(
        "--mode",
        choices=["manual", "auto"],
        default="manual",
        help=(
            "Execution mode. "
            "'manual': Rolling last 30/90 days from today. "
            "'auto': Last 1 or 3 completed calendar months (for scheduled jobs). "
            "(Default: manual)"
        ),
    )
    parser.add_argument(
        "--output",
        metavar="DIR",
        default=None,
        help="Directory to save the Excel report. (Default: ./output)",
    )

    return parser.parse_args(argv)


def resolve_period_dates(
    period_months: int,
    mode: str,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Çalışma moduna göre raporlama başlangıç ve bitiş tarihlerini hesaplar."""
    now_local = now or datetime.now(tz=TZ)
    today = now_local.date()

    if mode == "manual":
        days_back = 30 * period_months
        start_date = today - timedelta(days=days_back)
        period_start = datetime(
            start_date.year, start_date.month, start_date.day,
            0, 0, 0, tzinfo=TZ,
        )
        period_end = datetime(
            today.year, today.month, today.day,
            23, 59, 59, 999999, tzinfo=TZ,
        )

    elif mode == "auto":
        # Tamamlanmış en son takvim ayının bitişi (bu ayın 1'inden 1 gün öncesi)
        first_of_this_month = today.replace(day=1)
        last_month_end = first_of_this_month - timedelta(days=1)

        # Geriye dönük period_months kadar tamamlanmış takvim ayı
        start_month_idx = (
            last_month_end.year * 12
            + (last_month_end.month - 1)
            - (period_months - 1)
        )
        start_year = start_month_idx // 12
        start_month = (start_month_idx % 12) + 1

        period_start = datetime(
            start_year, start_month, 1,
            0, 0, 0, tzinfo=TZ,
        )
        period_end = datetime(
            last_month_end.year, last_month_end.month, last_month_end.day,
            23, 59, 59, 999999, tzinfo=TZ,
        )

    else:
        raise ValueError(f"Geçersiz mod: '{mode}'. 'manual' veya 'auto' olmalı.")

    logger.info(
        "Report period resolved [%s mode]: %s → %s",
        mode,
        period_start.strftime("%Y-%m-%d %H:%M:%S %Z"),
        period_end.strftime("%Y-%m-%d %H:%M:%S %Z"),
    )

    return period_start, period_end


def run(args: argparse.Namespace) -> None:
    """Executes the entire SLA analysis and reporting pipeline."""
    logger.info("=" * 60)
    logger.info("Cato SLA Reporter initialized.")
    logger.info(
        "Parameters: input='%s' | period=%d month(s) | mode=%s",
        args.input, args.period, args.mode,
    )
    logger.info("=" * 60)

    # 1. Raporlama dönemini hesapla
    period_start, period_end = resolve_period_dates(
        period_months=args.period,
        mode=args.mode,
    )

    # 2. Log dosyasını okut
    reader = CsvLogReader(args.input)
    raw_df = reader.read()

    if raw_df.empty:
        logger.error("Could not read data or CSV is empty. Aborting.")
        sys.exit(1)

    # 3. Veriyi dönüştür ve temizle
    clean_df = transform(raw_df)

    if clean_df.empty:
        logger.error(
            "No data remaining after transformation. "
            "Please check CSV format and columns."
        )
        sys.exit(1)

    # 4. Site bacaklarını tespit et (yalnızca dönem içindeki verilerden)
    period_mask = (
        (clean_df[COL_TIME] >= period_start)
        & (clean_df[COL_TIME] <= period_end)
    )
    leg_map = detect_legs(clean_df[period_mask])

    if not leg_map:
        logger.error("No sites detected in the period. Aborting.")
        sys.exit(1)

    all_sites = list(leg_map.keys())

    # 5. Kesinti analizi yap (State Machine)
    outages = detect_outages(
        df=clean_df,
        leg_map=leg_map,
        period_start=period_start,
        period_end=period_end,
    )

    # 6. SLA ve Availability değerlerini hesapla (gerçek takvim süresiyle)
    exact_period_minutes = (period_end - period_start).total_seconds() / 60.0
    summary_df = calculate_sla(
        outages=outages,
        all_sites=all_sites,
        period_months=args.period,
        total_minutes=exact_period_minutes,
    )

    # 7. Excel raporunu oluştur
    output_path = export_to_excel(
        summary_df=summary_df,
        outages=outages,
        period_months=args.period,
        output_dir=args.output,
        report_date=date.today(),
    )

    # Özet konsol çıktısı
    logger.info("=" * 60)
    logger.info("Process completed.")
    logger.info("Report period : %s", PERIOD_LABELS[args.period])
    logger.info("Total sites   : %d", len(summary_df))
    logger.info(
        "Sites passed SLA : %d",
        (summary_df["SLA Status"] == SLA_STATUS_PASSED).sum(),
    )
    logger.info(
        "Sites failed SLA : %d",
        (summary_df["SLA Status"] == SLA_STATUS_FAILED).sum(),
    )
    logger.info("Report file   : %s", output_path.resolve())
    logger.info("=" * 60)


def main() -> None:
    """Application entry point."""
    try:
        args = parse_args()
        run(args)
    except KeyboardInterrupt:
        logger.warning("Process interrupted by user.")
        sys.exit(0)
    except Exception as exc:
        logger.error("Unexpected error: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

