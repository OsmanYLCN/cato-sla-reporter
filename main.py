import argparse
import sys
import time
from datetime import date, datetime, timedelta

from config.settings import (
    COL_TIME,
    PERIOD_LABELS,
    SLA_STATUS_FAILED,
    SLA_STATUS_PASSED,
    TZ,
)
from data_ingestion.csv_reader import CsvLogReader
from data_ingestion.cato_api_client import CatoApiClient
from engine.leg_detector import detect_legs
from engine.sla_calculator import calculate_sla
from engine.state_machine import detect_outages
from preprocessing.transformer import transform
from reporting.excel_exporter import export_to_excel
from ui.terminal_ui import TerminalUI
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
            "  python main.py --source csv --input events.csv --period 1\n"
            "  python main.py --source api --period 1\n"
            "  python main.py --source api --date-from 2026-08-01 --date-to 2026-08-31\n"
        ),
    )

    parser.add_argument(
        "--source",
        choices=["csv", "api"],
        default="csv",
        help="Data ingestion source. (Default: csv)",
    )
    parser.add_argument(
        "--input",
        metavar="CSV_PATH",
        required=False,
        help="Path to Cato Networks log CSV file. Required if --source is csv.",
    )
    parser.add_argument(
        "--period",
        type=int,
        choices=[1, 3],
        required=False,
        metavar="{1,3}",
        help="Report period in months: 1 (Last 30 Days) or 3 (Last 90 Days).",
    )
    parser.add_argument(
        "--date-from",
        metavar="YYYY-MM-DD",
        help="Explicit start date for API mode (e.g., 2026-08-01). Overrides --period.",
    )
    parser.add_argument(
        "--date-to",
        metavar="YYYY-MM-DD",
        help="Explicit end date for API mode (e.g., 2026-08-31). Overrides --period.",
    )
    parser.add_argument(
        "--mode",
        choices=["manual", "auto"],
        default="manual",
        help=(
            "Execution mode. "
            "'manual': Rolling last 30/90 days from today. "
            "'auto': Last 1 or 3 completed calendar months. "
            "(Default: manual)"
        ),
    )
    parser.add_argument(
        "--output",
        metavar="DIR",
        default=None,
        help="Directory to save the Excel report. (Default: ./output)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Force interactive Terminal UI mode.",
    )

    args = parser.parse_args(argv)

    # Validation
    if args.source == "csv" and not args.input:
        parser.error("--input is required when --source is csv")

    if args.date_from or args.date_to:
        if not (args.date_from and args.date_to):
            parser.error("--date-from and --date-to must be provided together.")
        try:
            _dfrom = datetime.strptime(args.date_from, "%Y-%m-%d").date()
            _dto   = datetime.strptime(args.date_to,   "%Y-%m-%d").date()
        except ValueError as exc:
            parser.error(f"Invalid date format: {exc}. Use YYYY-MM-DD.")
        if _dfrom > _dto:
            parser.error(
                f"--date-from ({args.date_from}) cannot be later than "
                f"--date-to ({args.date_to})."
            )
        args.period = 0  # 0 indicates Custom Range

    if not args.period and args.period != 0:
        parser.error("--period is required unless --date-from and --date-to are provided.")

    return args


def resolve_period_dates(
    period_months: int,
    mode: str,
    date_from: str | None = None,
    date_to: str | None = None,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Çalışma moduna göre raporlama başlangıç ve bitiş tarihlerini hesaplar."""
    if date_from and date_to:
        start_date = datetime.strptime(date_from, "%Y-%m-%d").date()
        end_date = datetime.strptime(date_to, "%Y-%m-%d").date()
        period_start = datetime(
            start_date.year, start_date.month, start_date.day,
            0, 0, 0, tzinfo=TZ,
        )
        period_end = datetime(
            end_date.year, end_date.month, end_date.day,
            23, 59, 59, 999999, tzinfo=TZ,
        )
        logger.info(
            "Report period resolved [explicit dates]: %s → %s",
            period_start.strftime("%Y-%m-%d %H:%M:%S %Z"),
            period_end.strftime("%Y-%m-%d %H:%M:%S %Z"),
        )
        return period_start, period_end

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


def run(args: argparse.Namespace, tui: TerminalUI | None = None) -> None:
    """Executes the entire SLA analysis and reporting pipeline."""
    start_time = time.time()
    logger.info("=" * 60)
    logger.info("Cato SLA Reporter initialized.")
    logger.info(
        "Parameters: source='%s' | input='%s' | period=%d month(s) | mode=%s | date_from=%s | date_to=%s",
        args.source, args.input, args.period, args.mode, args.date_from, args.date_to,
    )
    logger.info("=" * 60)

    if tui:
        tui.print_pipeline_header()

    # 1. Raporlama dönemini hesapla
    period_start, period_end = resolve_period_dates(
        period_months=args.period,
        mode=args.mode,
        date_from=args.date_from,
        date_to=args.date_to,
    )
    if tui:
        tui.print_step(
            "Raporlama dönemi belirlendi",
            status="ok",
            detail=f"{period_start.strftime('%Y-%m-%d')} → {period_end.strftime('%Y-%m-%d')}",
        )

    # 2. Log dosyasını okut veya API'den çek
    if args.source == "api":
        logger.info("Fetching data from Cato GraphQL API...")
        if tui:
            tui.print_step("Cato GraphQL API'ye bağlanılıyor ve veriler çekiliyor...", status="running")
        client = CatoApiClient()
        raw_df = client.fetch_events(period_start, period_end)
        if tui:
            tui.print_step("Cato GraphQL API verisi başarıyla alındı", status="ok", detail=f"{len(raw_df):,} event")
    else:
        logger.info("Reading data from CSV file: %s", args.input)
        if tui:
            tui.print_step(f"CSV log verisi okunuyor...", status="running", detail=f"{args.input}")
        reader = CsvLogReader(args.input)
        raw_df = reader.read()
        if tui:
            tui.print_step("CSV log verisi başarıyla okundu", status="ok", detail=f"{len(raw_df):,} satır")

    if raw_df.empty:
        logger.error("Could not read data or CSV is empty. Aborting.")
        if tui:
            tui.print_step("Veri boş döndü veya okunamadı, işlem durduruldu.", status="error")
        sys.exit(1)

    # 3. Veriyi dönüştür ve temizle
    clean_df = transform(raw_df)

    if clean_df.empty:
        logger.error(
            "No data remaining after transformation. "
            "Please check CSV format and columns."
        )
        if tui:
            tui.print_step("Normalizasyon ve filtreleme sonrası geçerli kayıt kalmadı.", status="error")
        sys.exit(1)

    if tui:
        tui.print_step(
            "Veri temizleme, alias normalizasyonu ve saat dilimi dönüşümü tamamlandı",
            status="ok",
            detail=f"{len(clean_df):,} geçerli event",
        )

    # 4. Site bacaklarını tespit et (yalnızca dönem içindeki verilerden)
    period_mask = (
        (clean_df[COL_TIME] >= period_start)
        & (clean_df[COL_TIME] <= period_end)
    )
    leg_map = detect_legs(clean_df[period_mask])

    if not leg_map:
        logger.error("No sites detected in the period. Aborting.")
        if tui:
            tui.print_step("Dönem içinde aktif lokasyon tespit edilemedi.", status="error")
        sys.exit(1)

    all_sites = list(leg_map.keys())
    if tui:
        total_legs = sum(len(legs) for legs in leg_map.values())
        tui.print_step(
            f"{len(leg_map)} lokasyon ve WAN bacakları tespit edildi",
            status="ok",
            detail=f"{total_legs} bacak",
        )

    # 5. Kesinti analizi yap (State Machine)
    outages = detect_outages(
        df=clean_df,
        leg_map=leg_map,
        period_start=period_start,
        period_end=period_end,
    )
    total_downtime = sum(o.duration_minutes for o in outages)
    if tui:
        tui.print_step(
            "State Machine kesinti analizi tamamlandı",
            status="ok",
            detail=f"{len(outages)} kesinti kaydı",
        )

    # 6. SLA ve Availability değerlerini hesapla (gerçek takvim süresiyle)
    exact_period_minutes = (period_end - period_start).total_seconds() / 60.0
    summary_df = calculate_sla(
        outages=outages,
        all_sites=all_sites,
        period_months=args.period,
        total_minutes=exact_period_minutes,
    )
    if tui:
        tui.print_step("SLA ve Availability metrikleri hesaplandı", status="ok")

    # 7. Excel raporunu oluştur
    output_path = export_to_excel(
        summary_df=summary_df,
        outages=outages,
        period_months=args.period,
        output_dir=args.output,
        report_date=date.today(),
    )
    if tui:
        tui.print_step(
            "3 sekmeli Excel raporu oluşturuldu",
            status="ok",
            detail=output_path.name,
        )

    elapsed = time.time() - start_time
    passed_count = int((summary_df["SLA Status"] == SLA_STATUS_PASSED).sum())
    failed_count = int((summary_df["SLA Status"] == SLA_STATUS_FAILED).sum())

    # Özet konsol log çıktısı
    logger.info("=" * 60)
    logger.info("Process completed.")
    logger.info("Report period : %s", PERIOD_LABELS[args.period])
    logger.info("Total sites   : %d", len(summary_df))
    logger.info("Sites passed SLA : %d", passed_count)
    logger.info("Sites failed SLA : %d", failed_count)
    logger.info("Report file   : %s", output_path.resolve())
    logger.info("=" * 60)

    # İnteraktif TUI Yönetici Özet Kartı
    if tui:
        tui.print_completion_card(
            source=args.source,
            period_label=PERIOD_LABELS[args.period],
            period_start=period_start,
            period_end=period_end,
            total_sites=len(summary_df),
            passed=passed_count,
            failed=failed_count,
            outage_count=len(outages),
            total_downtime_min=total_downtime,
            output_path=str(output_path.resolve()),
            elapsed=elapsed,
        )


def main() -> None:
    """Application entry point."""
    try:
        is_interactive = (len(sys.argv) == 1 and sys.stdin.isatty()) or ("--interactive" in sys.argv)
        if is_interactive:
            tui = TerminalUI()
            tui.print_banner()
            source = tui.select_source()
            csv_path = None
            if source == "csv":
                csv_path = tui.select_csv_file()
            period, date_from, date_to = tui.select_period()

            args = argparse.Namespace(
                source=source,
                input=csv_path,
                period=period,
                date_from=date_from,
                date_to=date_to,
                mode="manual",
                output=None,
                interactive=True,
            )
            run(args, tui=tui)
        else:
            args = parse_args()
            run(args)
    except KeyboardInterrupt:
        logger.warning("Process interrupted by user.")
        print("\n[*] Program kullanıcı tarafından durduruldu.\n")
        sys.exit(0)
    except Exception as exc:
        logger.error("Unexpected error: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

