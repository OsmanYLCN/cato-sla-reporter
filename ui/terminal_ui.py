"""
ui/terminal_ui.py

Cato SLA Reporter — Terminal UI Module
=======================================
Dual-mode design:
  - Interactive TUI : kullanicinin sadece `python main.py` calistirdigi durum
  - Headless/Silent : arguman gecildigi veya sunucu otomasyonu durumu

Dis bagimlilik yok; yalnizca standart kutuphane kullanilir.
Windows 10/11 ANSI Virtual Terminal Processing otomatik aktif edilir.
"""

import re
import sys
import time
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Windows 10/11: ANSI renk destegini etkinlestir
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    try:
        import ctypes
        _kernel32 = ctypes.windll.kernel32
        _hOut = _kernel32.GetStdHandle(-11)
        _mode = ctypes.c_ulong()
        _kernel32.GetConsoleMode(_hOut, ctypes.byref(_mode))
        _kernel32.SetConsoleMode(_hOut, _mode.value | 0x0004)
    except Exception:
        pass

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")

# sample_data/ klasorune referans: proje kokunden iki seviye yukari
_SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent / "sample_data"

# ---------------------------------------------------------------------------
# UI Sinifi: Renk kodlari ve hizalama yardimcilari
# ---------------------------------------------------------------------------

class UI:
    """
    ANSI terminal renk kodlari ve metin hizalama yardimc sinifi.
    Terminale yazilmiyorsa (otomasyon/pipe) tum ANSI kodlari bos string olur.
    """

    IS_TTY: bool = sys.stdout.isatty()

    RESET   = "\033[0m"  if IS_TTY else ""
    BOLD    = "\033[1m"  if IS_TTY else ""
    DIM     = "\033[2m"  if IS_TTY else ""
    BLUE    = "\033[94m" if IS_TTY else ""
    CYAN    = "\033[96m" if IS_TTY else ""
    GREEN   = "\033[92m" if IS_TTY else ""
    YELLOW  = "\033[93m" if IS_TTY else ""
    RED     = "\033[91m" if IS_TTY else ""
    WHITE   = "\033[97m" if IS_TTY else ""
    GRAY    = "\033[90m" if IS_TTY else ""
    MAGENTA = "\033[95m" if IS_TTY else ""

    @staticmethod
    def vlen(s: str) -> int:
        """ANSI kacis dizilerini saymayin: gorunur karakter uzunlugunu dondurur."""
        return len(_ANSI_RE.sub("", str(s)))

    @staticmethod
    def pad(s: str, width: int, align: str = "left") -> str:
        """
        Dizeyi gorunur genislige gore hizalar, ANSI kodlari sayimda atlanir.
        align: 'left' | 'right' | 'center'
        """
        diff = max(0, width - UI.vlen(s))
        if align == "right":
            return (" " * diff) + s
        if align == "center":
            left = diff // 2
            return (" " * left) + s + (" " * (diff - left))
        return s + (" " * diff)


# ---------------------------------------------------------------------------
# TerminalUI: Tum etkilesimli panel ve istemleri kapsayan sinif
# ---------------------------------------------------------------------------

class TerminalUI:
    """
    Cato SLA Reporter icin etkilesimli terminal arayuzu.
    Tum kullanici istemi, dogrulama ve gorsel panel mantigi burada toplanir.
    """

    # -------------------------------------------------------------------
    # Dahili yardimcilar
    # -------------------------------------------------------------------

    def _safe_input(self, prompt: str) -> str:
        """input() sarmalayicisi — EOF ve KeyboardInterrupt guvenli cikar."""
        try:
            return input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{UI.DIM}[*] Guvenli cikis yapildi.{UI.RESET}\n")
            sys.exit(0)

    def _abort(self) -> None:
        print(f"\n{UI.DIM}[*] Guvenli cikis yapildi.{UI.RESET}\n")
        sys.exit(0)

    # -------------------------------------------------------------------
    # Banner
    # -------------------------------------------------------------------

    def print_banner(self, version: str = "v1.1.2") -> None:
        """Kurumsal baslik banner'ini yazdirir."""
        TITLE = "CATO NETWORKS  —  SD-WAN SLA & AVAILABILITY REPORTING ENGINE"
        SUB   = f"Version {version}    |    github.com/YOUR_ORG/cato-sla-reporter"
        W = 75
        print()
        print(f"{UI.CYAN}{UI.BOLD}╔" + "═" * W + "╗")
        print(f"║  {UI.pad(TITLE, W - 2)}║")
        print(f"║  {UI.GRAY}{UI.pad(SUB, W - 2)}{UI.RESET}{UI.CYAN}{UI.BOLD}║")
        print(f"╚" + "═" * W + f"╝{UI.RESET}")
        print()

    # -------------------------------------------------------------------
    # Kaynak secimi
    # -------------------------------------------------------------------

    def select_source(self) -> str:
        """
        Veri kaynagi sececisi.
        Returns: 'api' | 'csv'
        """
        print(f"{UI.BOLD}[?] Veri Kaynagini Secin:{UI.RESET}")
        print(f"{UI.DIM}  " + "─" * 57 + UI.RESET)
        print(f"  {UI.CYAN}(1){UI.RESET} {UI.BOLD}Cato GraphQL API{UI.RESET}   {UI.DIM}— Dogrudan Cloud erisimi  (Onerilen){UI.RESET}")
        print(f"  {UI.CYAN}(2){UI.RESET} {UI.BOLD}CSV Dosyasi{UI.RESET}        {UI.DIM}— Disari aktarilmis log dosyasindan{UI.RESET}")
        print(f"  {UI.RED}(Q){UI.RESET} Cikis")
        print(f"{UI.DIM}  " + "─" * 57 + UI.RESET)

        while True:
            choice = self._safe_input(
                f"\nSeciminiz [1, 2 veya Q]  (Varsayilan: {UI.CYAN}1{UI.RESET}): "
            )
            if choice in ("", "1"):
                print(f"  → {UI.GREEN}Secilen:{UI.RESET} Cato GraphQL API\n")
                return "api"
            if choice == "2":
                print(f"  → {UI.GREEN}Secilen:{UI.RESET} CSV Dosyasi\n")
                return "csv"
            if choice.upper() == "Q":
                self._abort()
            print(f"  {UI.RED}[!] Gecersiz secim. Lutfen 1, 2 veya Q girin.{UI.RESET}")

    # -------------------------------------------------------------------
    # CSV dosya secici
    # -------------------------------------------------------------------

    def _scan_csv_files(self) -> list[tuple[str, Path, float, float]]:
        """sample_data/ icindeki CSV'leri en yeniden eskiye sirali dondurur."""
        files = []
        if _SAMPLE_DATA_DIR.exists():
            for f in _SAMPLE_DATA_DIR.iterdir():
                if f.suffix.lower() == ".csv" and not f.name.startswith("~$"):
                    stat = f.stat()
                    files.append((f.name, f, stat.st_mtime, stat.st_size / 1024.0))
        files.sort(key=lambda x: x[2], reverse=True)
        return files

    def select_csv_file(self) -> str:
        """
        CSV dosyasi sececisi.
        sample_data/ icindeki dosyalari tarih+boyut ile listeler.
        Returns: secilen dosyanin yolu (str)
        """
        files = self._scan_csv_files()

        if not files:
            print(f"{UI.YELLOW}[!] 'sample_data/' klasorunde CSV dosyasi bulunamadi.{UI.RESET}")
            print( "    Lutfen ham CSV dosyanizi 'sample_data/' klasorune ekleyip tekrar deneyin.")
            print(f"    {UI.GRAY}veya{UI.RESET} tam dosya yolunu elle girebilirsiniz.\n")
            path = self._safe_input("    CSV dosya yolu [Q: cikis]: ")
            if path.upper() == "Q":
                self._abort()
            return path

        print(f"{UI.BOLD}[?] CSV Dosyasi Secin  (sample_data/):{UI.RESET}")
        print(f"{UI.DIM}  " + "─" * 67 + UI.RESET)
        for idx, (name, _fp, mtime, size_kb) in enumerate(files, start=1):
            dt_str   = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            size_str = f"{size_kb:,.0f} KB" if size_kb < 1024 else f"{size_kb/1024:,.1f} MB"
            tag      = f"  {UI.GREEN}[EN GUNCEL]{UI.RESET}" if idx == 1 else ""
            print(
                f"  {UI.CYAN}({idx}){UI.RESET} "
                f"{UI.pad(name, 42)}"
                f"{UI.DIM}[{dt_str} | {size_str:>8}]{UI.RESET}{tag}"
            )
        print(f"{UI.DIM}  " + "─" * 67 + UI.RESET)
        print(f"  {UI.YELLOW}(M){UI.RESET} Manuel dosya yolu gir...")
        print(f"  {UI.RED}(Q){UI.RESET} Cikis\n")

        while True:
            choice = self._safe_input(
                f"Dosya secin [1-{len(files)}, M veya Q]  (Varsayilan: {UI.CYAN}1{UI.RESET}): "
            )
            if choice in ("", "1"):
                f = files[0]
                print(f"  → {UI.GREEN}Secilen:{UI.RESET} {f[0]}\n")
                return str(f[1])
            if choice.upper() == "Q":
                self._abort()
            if choice.upper() == "M":
                path = self._safe_input("  CSV dosya yolu [Q: iptal]: ")
                if path.upper() == "Q":
                    self._abort()
                if path:
                    return path
                continue
            if choice.isdigit():
                val = int(choice)
                if 1 <= val <= len(files):
                    f = files[val - 1]
                    print(f"  → {UI.GREEN}Secilen:{UI.RESET} {f[0]}\n")
                    return str(f[1])
                print(f"  {UI.RED}[!] Gecersiz numara. 1-{len(files)} arasinda bir deger girin.{UI.RESET}")
            else:
                if Path(choice).exists():
                    return choice
                print(f"  {UI.RED}[!] Gecersiz secim.{UI.RESET}")

    # -------------------------------------------------------------------
    # Donem / Tarih araligI secimi
    # -------------------------------------------------------------------

    def select_period(self) -> tuple[int, str | None, str | None]:
        """
        Raporlama donemi sececisi.
        Returns: (period_months, date_from, date_to)
          period_months = 0  => ozel tarih araligi
        """
        print(f"{UI.BOLD}[?] Raporlama Donemi:{UI.RESET}")
        print(f"{UI.DIM}  " + "─" * 57 + UI.RESET)
        print(f"  {UI.CYAN}(1){UI.RESET} Son 1 Ay        {UI.DIM}— Last 1 Month  (son 30 gun){UI.RESET}")
        print(f"  {UI.CYAN}(2){UI.RESET} Son 3 Ay        {UI.DIM}— Last 3 Months (son 90 gun){UI.RESET}")
        print(f"  {UI.CYAN}(3){UI.RESET} Ozel Tarih      {UI.DIM}— Custom Date Range (YYYY-MM-DD){UI.RESET}")
        print(f"  {UI.RED}(Q){UI.RESET} Cikis")
        print(f"{UI.DIM}  " + "─" * 57 + UI.RESET)

        while True:
            choice = self._safe_input(
                f"\nSeciminiz [1, 2, 3 veya Q]  (Varsayilan: {UI.CYAN}1{UI.RESET}): "
            )
            if choice in ("", "1"):
                print(f"  → {UI.GREEN}Secilen:{UI.RESET} Son 1 Ay\n")
                return (1, None, None)
            if choice == "2":
                print(f"  → {UI.GREEN}Secilen:{UI.RESET} Son 3 Ay\n")
                return (3, None, None)
            if choice == "3":
                date_from, date_to = self._select_custom_dates()
                return (0, date_from, date_to)
            if choice.upper() == "Q":
                self._abort()
            print(f"  {UI.RED}[!] Gecersiz secim.{UI.RESET}")

    def _select_custom_dates(self) -> tuple[str, str]:
        """Ozel tarih araligi istemi — format ve siralama dogrulamasi yapar."""
        print(f"\n{UI.BOLD}[?] Ozel Tarih Araligi:{UI.RESET}  {UI.DIM}(Format: YYYY-MM-DD  |  Q: iptal){UI.RESET}")
        while True:
            date_from = self._safe_input(f"  {UI.CYAN}Baslangic tarihi{UI.RESET} (date-from): ")
            if date_from.upper() == "Q":
                self._abort()
            date_to = self._safe_input(f"  {UI.CYAN}Bitis tarihi{UI.RESET}     (date-to)  : ")
            if date_to.upper() == "Q":
                self._abort()
            try:
                dfrom = datetime.strptime(date_from, "%Y-%m-%d").date()
                dto   = datetime.strptime(date_to,   "%Y-%m-%d").date()
            except ValueError:
                print(f"  {UI.RED}[!] Gecersiz tarih formati. YYYY-MM-DD kullanin.{UI.RESET}")
                continue
            if dfrom > dto:
                print(f"  {UI.RED}[!] Baslangic tarihi bitis tarihinden sonra olamaz.{UI.RESET}")
                continue
            print(f"  → {UI.GREEN}Secilen:{UI.RESET} {date_from}  →  {date_to}\n")
            return date_from, date_to

    # -------------------------------------------------------------------
    # Pipeline ilerleme goruntuleme
    # -------------------------------------------------------------------

    def print_pipeline_header(self) -> None:
        """Pipeline baslik satirini yazdirir."""
        print(f"{UI.BOLD}{UI.CYAN}[*] Pipeline baslatiliyor...{UI.RESET}\n")

    def print_step(self, message: str, status: str = "ok", detail: str = "") -> None:
        """
        Tekil bir pipeline adimini yazdirir.

        status degerleri:
            'ok'      → [✓] yesil
            'warn'    → [⚠] sari
            'error'   → [✗] kirmizi
            'running' → [→] cyan
        """
        _icons = {
            "ok":      f"{UI.GREEN}[✓]{UI.RESET}",
            "warn":    f"{UI.YELLOW}[⚠]{UI.RESET}",
            "error":   f"{UI.RED}[✗]{UI.RESET}",
            "running": f"{UI.CYAN}[→]{UI.RESET}",
        }
        icon       = _icons.get(status, _icons["ok"])
        detail_str = f"  {UI.DIM}({detail}){UI.RESET}" if detail else ""
        print(f"  {icon} {message}{detail_str}")

    # -------------------------------------------------------------------
    # Tamamlanma karti
    # -------------------------------------------------------------------

    def print_completion_card(
        self,
        *,
        source: str,
        period_label: str,
        period_start: datetime,
        period_end: datetime,
        total_sites: int,
        passed: int,
        failed: int,
        outage_count: int,
        total_downtime_min: float,
        output_path: str,
        elapsed: float,
    ) -> None:
        """
        Pipeline sonunda yonetici ozet kartini gosterir.
        Tek bakista tum kritik metrikleri sunar.
        """
        threshold = 99.90
        sla_rate  = (passed / total_sites * 100) if total_sites > 0 else 0.0
        sla_ok    = sla_rate >= threshold
        sla_color = UI.GREEN if sla_ok else UI.RED
        sla_tag   = "PASSED" if sla_ok else "FAILED"

        src_label   = "Cato GraphQL API" if source == "api" else "CSV Dosyasi"
        period_str  = (
            f"{period_start.strftime('%Y-%m-%d')}  →  {period_end.strftime('%Y-%m-%d')}"
        )

        # Downtime'i insan okunur formata cevir
        total_secs  = int(total_downtime_min * 60)
        h, rem      = divmod(total_secs, 3600)
        m, s        = divmod(rem, 60)
        if h:
            downtime_str = f"{h}s {m}d {s}sn"
        elif m:
            downtime_str = f"{m}d {s}sn"
        else:
            downtime_str = f"{s}sn"

        W = 78
        header = "ISLEM TAMAMLANDI  —  YONETICI OZET RAPORU"

        print()
        print(f"{UI.BOLD}╔" + "═" * W + "╗")
        print(f"║{UI.GREEN}{UI.pad(header, W, align='center')}{UI.RESET}{UI.BOLD}║")
        print("╠" + "═" * W + "╣" + UI.RESET)

        def _row(label: str, value: str) -> None:
            lbl     = UI.pad(label, 27)
            content = f"  {lbl} : {value}"
            print(f"{UI.BOLD}║{UI.RESET}{UI.pad(content, W)}{UI.BOLD}║{UI.RESET}")

        def _div() -> None:
            print(f"{UI.BOLD}╟" + "─" * W + f"╢{UI.RESET}")

        _row(f"{UI.CYAN}Raporlama Donemi{UI.RESET}", f"{period_label}  {UI.DIM}({period_str}){UI.RESET}")
        _row(f"{UI.CYAN}Veri Kaynagi{UI.RESET}",     src_label)
        _div()
        _row(f"{UI.BOLD}Incelenen Lokasyon{UI.RESET}", f"{total_sites} site")
        _row(
            f"{UI.BOLD}SLA Hedef Uyumu{UI.RESET}",
            f"{UI.GREEN}{passed} Passed{UI.RESET}  /  "
            f"{UI.RED}{failed} Failed{UI.RESET}  "
            f"{UI.DIM}(Esik: %{threshold:.2f}){UI.RESET}",
        )
        _row(
            f"{UI.BOLD}Genel SLA Basarisi{UI.RESET}",
            f"{sla_color}{UI.BOLD}{sla_rate:.2f}%  [ {sla_tag} ]{UI.RESET}",
        )
        _div()
        _row(
            f"{UI.DIM}Toplam Kesinti{UI.RESET}",
            f"{outage_count} adet  {UI.DIM}(Toplam Sure: {downtime_str}){UI.RESET}",
        )
        _row(f"{UI.DIM}Islem Suresi{UI.RESET}",  f"{elapsed:.2f} saniye")
        _div()
        _row(f"{UI.YELLOW}Uretilen Rapor{UI.RESET}", f"{UI.WHITE}{output_path}{UI.RESET}")
        print(f"{UI.BOLD}╚" + "═" * W + f"╝{UI.RESET}\n")
