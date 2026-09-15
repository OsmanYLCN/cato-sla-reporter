import sys
from datetime import datetime, date
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from ui.terminal_ui import UI, TerminalUI
from config.settings import TZ


class TestUIHelpers:
    """UI static formatting helper tests."""

    def test_vlen_ignores_ansi_codes(self):
        colored_text = f"\033[92mHello World\033[0m"
        assert UI.vlen(colored_text) == 11

    def test_vlen_plain_string(self):
        assert UI.vlen("Test string") == 11

    def test_pad_left(self):
        padded = UI.pad("Item", 10, align="left")
        assert padded == "Item      "
        assert UI.vlen(padded) == 10

    def test_pad_right(self):
        padded = UI.pad("Item", 10, align="right")
        assert padded == "      Item"
        assert UI.vlen(padded) == 10

    def test_pad_center(self):
        padded = UI.pad("Item", 10, align="center")
        assert padded == "   Item   "
        assert UI.vlen(padded) == 10


class TestTerminalUIComponents:
    """TerminalUI visual component render tests."""

    def test_print_banner_does_not_raise(self, capsys):
        tui = TerminalUI()
        tui.print_banner()
        captured = capsys.readouterr()
        assert "CATO NETWORKS" in captured.out
        assert "SLA & AVAILABILITY REPORTING ENGINE" in captured.out

    def test_print_step_renders_all_statuses(self, capsys):
        tui = TerminalUI()
        tui.print_step("Step 1", status="ok", detail="detail 1")
        tui.print_step("Step 2", status="warn", detail="detail 2")
        tui.print_step("Step 3", status="error", detail="detail 3")
        tui.print_step("Step 4", status="running", detail="detail 4")
        captured = capsys.readouterr()
        assert "Step 1" in captured.out
        assert "detail 1" in captured.out
        assert "Step 2" in captured.out
        assert "Step 3" in captured.out
        assert "Step 4" in captured.out

    def test_print_completion_card(self, capsys):
        tui = TerminalUI()
        now = datetime.now(tz=TZ)
        tui.print_completion_card(
            source="api",
            period_label="Last 1 Month",
            period_start=now,
            period_end=now,
            total_sites=10,
            passed=9,
            failed=1,
            outage_count=2,
            total_downtime_min=45.5,
            output_path="output/test_report.xlsx",
            elapsed=3.14,
        )
        captured = capsys.readouterr()
        assert "ISLEM TAMAMLANDI" in captured.out
        assert "10 site" in captured.out
        assert "9 Passed" in captured.out
        assert "1 Failed" in captured.out
        assert "output/test_report.xlsx" in captured.out


class TestTerminalUIInteractiveInputs:
    """Interactive input prompt tests with mocks."""

    def test_select_source_default_is_api(self):
        tui = TerminalUI()
        with patch.object(tui, "_safe_input", return_value=""):
            assert tui.select_source() == "api"

    def test_select_source_explicit_choices(self):
        tui = TerminalUI()
        with patch.object(tui, "_safe_input", return_value="1"):
            assert tui.select_source() == "api"
        with patch.object(tui, "_safe_input", return_value="2"):
            assert tui.select_source() == "csv"

    def test_select_period_month_options(self):
        tui = TerminalUI()
        with patch.object(tui, "_safe_input", return_value="1"):
            assert tui.select_period() == (1, None, None)
        with patch.object(tui, "_safe_input", return_value="2"):
            assert tui.select_period() == (3, None, None)

    def test_select_period_custom_dates(self):
        tui = TerminalUI()
        with patch.object(tui, "_safe_input", side_effect=["3", "2026-08-01", "2026-08-31"]):
            period, dfrom, dto = tui.select_period()
            assert period == 0
            assert dfrom == "2026-08-01"
            assert dto == "2026-08-31"

    def test_select_csv_file_with_scanned_files(self):
        tui = TerminalUI()
        mock_files = [("sample.csv", Path("sample_data/sample.csv"), 1000.0, 50.0)]
        with patch.object(tui, "_scan_csv_files", return_value=mock_files):
            with patch.object(tui, "_safe_input", return_value="1"):
                chosen_file = tui.select_csv_file()
                assert chosen_file.endswith(".csv")

    def test_select_csv_file_when_empty_prompts_manual_path(self):
        tui = TerminalUI()
        with patch.object(tui, "_scan_csv_files", return_value=[]):
            with patch.object(tui, "_safe_input", return_value="custom/path/test.csv"):
                chosen_file = tui.select_csv_file()
                assert chosen_file == "custom/path/test.csv"
