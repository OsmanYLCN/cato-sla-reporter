import pytest
import argparse
from datetime import datetime, date
from unittest.mock import patch
from main import parse_args, resolve_period_dates, run
from config.settings import TZ


def test_parse_args_csv_default():
    args = parse_args(["--input", "test.csv", "--period", "1"])
    assert args.source == "csv"
    assert args.input == "test.csv"
    assert args.period == 1
    assert args.mode == "manual"
    assert args.date_from is None
    assert args.date_to is None

def test_parse_args_api_mode():
    args = parse_args(["--source", "api", "--period", "3"])
    assert args.source == "api"
    assert args.input is None
    assert args.period == 3
    assert args.mode == "manual"

def test_parse_args_api_with_custom_dates():
    args = parse_args(["--source", "api", "--date-from", "2026-08-01", "--date-to", "2026-08-31"])
    assert args.source == "api"
    assert args.period == 0
    assert args.date_from == "2026-08-01"
    assert args.date_to == "2026-08-31"

def test_parse_args_missing_input_for_csv():
    with pytest.raises(SystemExit):
        parse_args(["--source", "csv", "--period", "1"])

def test_parse_args_missing_date_to():
    with pytest.raises(SystemExit):
        parse_args(["--source", "api", "--date-from", "2026-08-01"])

def test_resolve_period_dates_with_custom_dates():
    start, end = resolve_period_dates(
        period_months=0,
        mode="manual",
        date_from="2026-08-01",
        date_to="2026-08-31"
    )
    assert start == datetime(2026, 8, 1, 0, 0, 0, tzinfo=TZ)
    assert end == datetime(2026, 8, 31, 23, 59, 59, 999999, tzinfo=TZ)

@patch("main.CatoApiClient")
@patch("main.transform")
@patch("main.detect_legs")
@patch("main.detect_outages")
@patch("main.calculate_sla")
@patch("main.export_to_excel")
def test_run_api_source(mock_export, mock_calc_sla, mock_detect_outages, mock_detect_legs, mock_transform, mock_api_client):
    import pandas as pd
    
    # Arrange
    mock_client_instance = mock_api_client.return_value
    mock_client_instance.fetch_events.return_value = pd.DataFrame({"col": [1, 2]})
    
    mock_transform.return_value = pd.DataFrame({"col": [1, 2], "time": [datetime.now(TZ), datetime.now(TZ)]})
    mock_detect_legs.return_value = {"SiteA": ["test"]}
    mock_detect_outages.return_value = []
    
    # Mocking export logic properly
    mock_calc_sla.return_value = pd.DataFrame([{"SLA Status": "Passed"}])
    mock_export.return_value.resolve.return_value = "report.xlsx"

    args = argparse.Namespace(
        source="api",
        input=None,
        period=1,
        mode="manual",
        date_from=None,
        date_to=None,
        output=None
    )

    # Act
    run(args)
    
    # Assert
    mock_api_client.assert_called_once()
    mock_client_instance.fetch_events.assert_called_once()
