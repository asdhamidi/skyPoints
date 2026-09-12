"""
Generates fixture files reproducing the real per-country source shapes
(docs/01_Design_Specification.md §2, docs/05_Source_Data_Analysis.md §1),
including the known data-quality edge cases each source carries, plus a
redemption JSON feed. Used for local dbt-duckdb development and the live demo
(docs/03_Technical_Build_Plan.md §3, §6).

Public API:
    build_aus_rows(run_date) -> list[dict]
    build_ind_rows(run_date) -> list[dict]
    build_usa_rows(run_date) -> list[dict]
    build_redemption_payloads(run_date) -> list[dict]
    generate(run_date, out_dir) -> dict[str, Path]

CLI:
    python generate_sample_feed.py --run-date 2024-01-15 --out-dir landing/
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path

from openpyxl import Workbook

AUS_COLUMNS = ["Unique ID", "Member Name", "Tier Type", "Date of Birth", "Date of Enrollment", "Date of Flight"]
IND_COLUMNS = ["ID", "Name", "DOB", "TierCode", "EnrollmentDate", "Individual or Corporate", "Flight Date"]
USA_COLUMNS = ["ID", "Name", "TierCode", "EnrollmentDate", "FlightDate"]


def build_aus_rows(run_date: date) -> list[dict]:
    """Reproduces AUS.xlsx (docs/05 §1): member 1's DOB is the literal string
    "NULL" and member 2's enrollment date is the invalid string "2021-13-13" —
    both real defects found in the supplied source file, not synthetic ones."""
    return [
        {
            "Unique ID": 1, "Member Name": "Mike", "Tier Type": "PLT",
            "Date of Birth": "NULL",
            "Date of Enrollment": date(2022, 5, 11), "Date of Flight": date(2022, 8, 1),
        },
        {
            "Unique ID": 2, "Member Name": "Jonnathan", "Tier Type": "GLD",
            "Date of Birth": date(1997, 12, 13),
            "Date of Enrollment": "2021-13-13", "Date of Flight": date(2022, 1, 5),
        },
        {
            "Unique ID": 3, "Member Name": "Cristina", "Tier Type": "SLV",
            "Date of Birth": date(1998, 3, 12),
            "Date of Enrollment": date(2022, 3, 12), "Date of Flight": date(2022, 3, 20),
        },
    ]


def build_ind_rows(run_date: date) -> list[dict]:
    """Reproduces IND.csv (docs/05 §1): US-style M/D/YYYY text dates. Member 2's
    TierCode alternates by day parity, giving the attribute-history snapshot
    (docs/01 §7.3) a real change to version across two run dates — see
    test_second_run_date_changes_a_tracked_attribute."""
    rahul_tier = "GLD" if run_date.day % 2 == 1 else "PLT"
    return [
        {
            "ID": 1, "Name": "Vikas", "DOB": "12/1/1998", "TierCode": "SLV",
            "EnrollmentDate": "1/1/2022", "Individual or Corporate": "I", "Flight Date": "6/15/2022",
        },
        {
            "ID": 2, "Name": "Rahul", "DOB": "8/13/1982", "TierCode": rahul_tier,
            "EnrollmentDate": "3/5/2022", "Individual or Corporate": "C", "Flight Date": "3/10/2022",
        },
        {
            "ID": 3, "Name": "Sameer", "DOB": "8/13/1952", "TierCode": "GLD",
            "EnrollmentDate": "2/20/2022", "Individual or Corporate": "I", "Flight Date": "2/25/2022",
        },
    ]


def build_usa_rows(run_date: date) -> list[dict]:
    """Reproduces USA.csv (docs/05 §1): no DOB column at all, and concatenated
    digit dates with no delimiter — row 2's values ("1052022", "1152022") are
    genuinely ambiguous (two valid calendar splits each), not just ugly."""
    return [
        {"ID": 1, "Name": "Sam", "TierCode": "PLT", "EnrollmentDate": "6152022", "FlightDate": "8202022"},
        {"ID": 2, "Name": "John", "TierCode": "SLV", "EnrollmentDate": "1052022", "FlightDate": "1152022"},
        {"ID": 3, "Name": "Mike", "TierCode": "GLD", "EnrollmentDate": "12282021", "FlightDate": "12302021"},
    ]


def build_redemption_payloads(run_date: date) -> list[dict]:
    """One JSON document per member per day (docs/01 §2), referencing a
    member_id that actually exists in this run's IND rows."""
    feed_date = run_date.strftime("%Y%m%d")
    return [
        {
            "member_id": "1",
            "feed_date": feed_date,
            "redemptions": [
                {"txn_id": "RX10091", "txn_date": feed_date, "partner": "AeroLink",
                 "miles_redeemed": 12000, "status": "COMPLETED"},
                {"txn_id": "RX10092", "txn_date": feed_date, "partner": "SkyPoints",
                 "miles_redeemed": 5000, "status": "PENDING"},
            ],
        },
    ]


def _write_xlsx(rows: list[dict], columns: list[str], path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(columns)
    for row in rows:
        ws.append([row[c] for c in columns])
    wb.save(path)


def _write_csv(rows: list[dict], columns: list[str], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _write_ndjson(payloads: list[dict], path: Path) -> None:
    """Newline-delimited JSON: one member's document per line, matching how
    Snowflake ingests a multi-record daily JSON feed without loading a single
    giant array into memory (docs/01 §2 — "one document per member per day")."""
    with open(path, "w", encoding="utf-8") as f:
        for payload in payloads:
            f.write(json.dumps(payload))
            f.write("\n")


def generate(run_date: date, out_dir: Path) -> dict[str, Path]:
    """Writes all four daily fixture files and returns their paths, keyed by
    source name (aus, ind, usa, redemption)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = run_date.strftime("%Y%m%d")

    paths = {
        "aus": out_dir / f"aus_member_{stamp}.xlsx",
        "ind": out_dir / f"ind_member_{stamp}.csv",
        "usa": out_dir / f"usa_member_{stamp}.csv",
        "redemption": out_dir / f"redemption_{stamp}.json",
    }

    _write_xlsx(build_aus_rows(run_date), AUS_COLUMNS, paths["aus"])
    _write_csv(build_ind_rows(run_date), IND_COLUMNS, paths["ind"])
    _write_csv(build_usa_rows(run_date), USA_COLUMNS, paths["usa"])
    _write_ndjson(build_redemption_payloads(run_date), paths["redemption"])

    return paths


def _parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--out-dir", default="landing", help="output directory (default: landing/)")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    run_date = date.fromisoformat(args.run_date)
    paths = generate(run_date, Path(args.out_dir))
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
