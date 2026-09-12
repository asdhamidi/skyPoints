"""
Tests for airflow/scripts/convert_aus_xlsx_to_csv.py — written before the implementation
exists (docs/04_Engineering_Practices.md §1, step 1: Red).

Snowflake has no native Excel file format (docs/02_Tech_Stack_Specification.md §2), so
AUS.xlsx is converted to CSV ahead of staging. The two defects catalogued in
docs/01_Design_Specification.md §2 / docs/05_Source_Data_Analysis.md §1 (a literal "NULL"
string, and an invalid date stored as text) must survive this conversion unchanged —
CSV_FORMAT's NULL_IF (setup/snowflake_bootstrap.sql §4) is what actually turns "NULL" into
a true null, at load time, not this script.

Expected public API (airflow/scripts/convert_aus_xlsx_to_csv.py):
    convert(xlsx_path: Path, csv_path: Path) -> Path
"""
import csv
import datetime as dt

import pytest
from openpyxl import Workbook

# Deliberately a plain import, not pytest.importorskip: until this script exists,
# collection must fail loudly (red), not skip quietly.
import convert_aus_xlsx_to_csv


def _write_workbook(path, rows):
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_preserves_header_row(tmp_path):
    xlsx_path = tmp_path / "aus.xlsx"
    _write_workbook(xlsx_path, [
        ["Unique ID", "Member Name", "Tier Type", "Date of Birth", "Date of Enrollment", "Date of Flight"],
        [1, "Mike", "PLT", "NULL", dt.datetime(2022, 5, 11), dt.datetime(2022, 8, 1)],
    ])
    csv_path = tmp_path / "aus.csv"

    convert_aus_xlsx_to_csv.convert(xlsx_path, csv_path)

    with open(csv_path, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header == [
        "Unique ID", "Member Name", "Tier Type",
        "Date of Birth", "Date of Enrollment", "Date of Flight",
    ]


def test_preserves_literal_null_string_as_text(tmp_path):
    xlsx_path = tmp_path / "aus.xlsx"
    _write_workbook(xlsx_path, [
        ["Unique ID", "Member Name", "Tier Type", "Date of Birth", "Date of Enrollment", "Date of Flight"],
        [1, "Mike", "PLT", "NULL", dt.datetime(2022, 5, 11), dt.datetime(2022, 8, 1)],
    ])
    csv_path = tmp_path / "aus.csv"

    convert_aus_xlsx_to_csv.convert(xlsx_path, csv_path)

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["Date of Birth"] == "NULL", (
        "the literal string 'NULL' must pass through as text — NULL_IF at the "
        "Snowflake file-format level is what converts it to a true null, not this script"
    )


def test_preserves_invalid_date_string_as_text(tmp_path):
    xlsx_path = tmp_path / "aus.xlsx"
    _write_workbook(xlsx_path, [
        ["Unique ID", "Member Name", "Tier Type", "Date of Birth", "Date of Enrollment", "Date of Flight"],
        [2, "Jonnathan", "GLD", dt.datetime(1997, 12, 13), "2021-13-13", dt.datetime(2022, 1, 5)],
    ])
    csv_path = tmp_path / "aus.csv"

    convert_aus_xlsx_to_csv.convert(xlsx_path, csv_path)

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["Date of Enrollment"] == "2021-13-13", (
        "an already-invalid date string must not be silently reinterpreted or dropped"
    )


def test_formats_real_datetime_cells_deterministically(tmp_path):
    xlsx_path = tmp_path / "aus.xlsx"
    _write_workbook(xlsx_path, [
        ["Unique ID", "Member Name", "Tier Type", "Date of Birth", "Date of Enrollment", "Date of Flight"],
        [3, "Cristina", "SLV", dt.datetime(1998, 3, 12), dt.datetime(2022, 3, 12), dt.datetime(2022, 3, 20)],
    ])
    csv_path = tmp_path / "aus.csv"

    convert_aus_xlsx_to_csv.convert(xlsx_path, csv_path)

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # ISO 8601 date, unambiguous, matches the format masks used elsewhere in the pipeline
    assert rows[0]["Date of Birth"] == "1998-03-12"
    assert rows[0]["Date of Enrollment"] == "2022-03-12"
    assert rows[0]["Date of Flight"] == "2022-03-20"


def test_raises_clearly_on_missing_source_file(tmp_path):
    missing = tmp_path / "does_not_exist.xlsx"
    csv_path = tmp_path / "out.csv"
    with pytest.raises(FileNotFoundError):
        convert_aus_xlsx_to_csv.convert(missing, csv_path)
