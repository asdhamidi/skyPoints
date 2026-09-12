"""
Generates fixture files reproducing the real per-country source shapes
(docs/01_Design_Specification.md §2, docs/05_Source_Data_Analysis.md §1),
including the known data-quality edge cases each source carries, plus a
redemption JSON feed. Used for local dbt-duckdb development and the live demo
(docs/03_Technical_Build_Plan.md §3, §6).

Every build_*_rows function returns a small, fixed set of hand-crafted
"golden" rows first (the specific edge cases documented below and asserted on
throughout tests/test_generate_sample_feed.py), followed by `bulk_count`
additional synthetic rows for volume. Bulk rows are deterministic (seeded per
source/run_date) and deliberately well-formed — they exercise scale, not the
edge cases, which stay isolated to the small golden set.

Public API:
    build_aus_rows(run_date, bulk_count=0) -> list[dict]
    build_ind_rows(run_date, bulk_count=0) -> list[dict]
    build_usa_rows(run_date, bulk_count=0) -> list[dict]
    build_redemption_payloads(run_date, bulk_count=0) -> list[dict]
    generate(run_date, out_dir, bulk_count=0) -> dict[str, Path]

CLI:
    python generate_sample_feed.py --run-date 2024-01-15 --out-dir landing/
    (defaults to 250,000 bulk records per source; override with --record-count)
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import date
from pathlib import Path

from openpyxl import Workbook

AUS_COLUMNS = ["Unique ID", "Member Name", "Tier Type", "Date of Birth", "Date of Enrollment", "Date of Flight"]
IND_COLUMNS = ["ID", "Name", "DOB", "TierCode", "EnrollmentDate", "Individual or Corporate", "Flight Date"]
USA_COLUMNS = ["ID", "Name", "TierCode", "EnrollmentDate", "FlightDate"]

DEFAULT_BULK_RECORD_COUNT = 250_000

# Bulk IDs live in disjoint per-source ranges, far above the golden 1-4 range.
# This is deliberate: the golden rows reproduce the real files' actual
# collision (AUS/IND/USA all number members 1, 2, 3... — docs/01 §3, §7), but
# bulk data needs the opposite property so a bulk redemption can be
# constructed to resolve to exactly one country, to demonstrate volume
# without flooding the pipeline with ambiguous matches.
AUS_BULK_ID_OFFSET = 1_000_000
IND_BULK_ID_OFFSET = 2_000_000
USA_BULK_ID_OFFSET = 3_000_000

_TIER_CODES = ["PLT", "GLD", "SLV"]
_PARTNERS = ["AeroLink", "SkyPoints", "GlobalWings"]
_STATUSES = ["COMPLETED", "PENDING"]


def _rng(run_date: date, source: str) -> random.Random:
    """Deterministic per-source, per-day random stream — same run_date and
    source always produce the same bulk rows, so a demo run is reproducible."""
    return random.Random(f"{source}-{run_date.isoformat()}")


def build_aus_rows(run_date: date, bulk_count: int = 0) -> list[dict]:
    """Reproduces AUS.xlsx (docs/05 §1): member 1's DOB is the literal string
    "NULL" and member 2's enrollment date is the invalid string "2021-13-13" —
    both real defects found in the supplied source file, not synthetic ones."""
    rows = [
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
    rng = _rng(run_date, "aus")
    for i in range(bulk_count):
        rows.append({
            "Unique ID": AUS_BULK_ID_OFFSET + i,
            "Member Name": f"AusMember{i}",
            "Tier Type": rng.choice(_TIER_CODES),
            "Date of Birth": date(rng.randint(1950, 2005), rng.randint(1, 12), rng.randint(1, 28)),
            "Date of Enrollment": date(rng.randint(2015, 2023), rng.randint(1, 12), rng.randint(1, 28)),
            "Date of Flight": date(rng.randint(2023, 2024), rng.randint(1, 12), rng.randint(1, 28)),
        })
    return rows


def build_ind_rows(run_date: date, bulk_count: int = 0) -> list[dict]:
    """Reproduces IND.csv (docs/05 §1): US-style M/D/YYYY text dates. Member 2's
    TierCode alternates by day parity, giving the attribute-history snapshot
    (docs/01 §7.3) a real change to version across two run dates — see
    test_second_run_date_changes_a_tracked_attribute.

    Member 4 (Priya) is a demo-only addition beyond the real IND.csv sample:
    her ID (4) doesn't exist in AUS or USA's 1-3 range, so a redemption
    referencing her is the only one that resolves to exactly one country
    under the join classification in docs/01 §7 — everything in 1-3 matches
    all three sources at once (docs/01 §7, §9) and can't demonstrate a clean
    resolved match on its own."""
    rahul_tier = "GLD" if run_date.day % 2 == 1 else "PLT"
    rows = [
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
        {
            "ID": 4, "Name": "Priya", "DOB": "5/22/1990", "TierCode": "SLV",
            "EnrollmentDate": "4/10/2023", "Individual or Corporate": "I", "Flight Date": "4/15/2023",
        },
    ]
    rng = _rng(run_date, "ind")
    for i in range(bulk_count):
        rows.append({
            "ID": IND_BULK_ID_OFFSET + i,
            "Name": f"IndMember{i}",
            "DOB": f"{rng.randint(1, 12)}/{rng.randint(1, 28)}/{rng.randint(1950, 2005)}",
            "TierCode": rng.choice(_TIER_CODES),
            "EnrollmentDate": f"{rng.randint(1, 12)}/{rng.randint(1, 28)}/{rng.randint(2015, 2023)}",
            "Individual or Corporate": rng.choice(["I", "C"]),
            "Flight Date": f"{rng.randint(1, 12)}/{rng.randint(1, 28)}/{rng.randint(2023, 2024)}",
        })
    return rows


def build_usa_rows(run_date: date, bulk_count: int = 0) -> list[dict]:
    """Reproduces USA.csv (docs/05 §1): no DOB column at all, and concatenated
    digit dates with no delimiter — row 2's values ("1052022", "1152022") are
    genuinely ambiguous (two valid calendar splits each), not just ugly.

    Bulk rows always zero-pad to 8-digit MMDDYYYY, which docs/01 §4 established
    is the one digit-count that's always unambiguous (a 7-digit value is what
    creates the two-way split) — bulk data exercises volume, not the
    quarantine path the golden John row already covers."""
    rows = [
        {"ID": 1, "Name": "Sam", "TierCode": "PLT", "EnrollmentDate": "6152022", "FlightDate": "8202022"},
        {"ID": 2, "Name": "John", "TierCode": "SLV", "EnrollmentDate": "1052022", "FlightDate": "1152022"},
        {"ID": 3, "Name": "Mike", "TierCode": "GLD", "EnrollmentDate": "12282021", "FlightDate": "12302021"},
    ]
    rng = _rng(run_date, "usa")
    for i in range(bulk_count):
        rows.append({
            "ID": USA_BULK_ID_OFFSET + i,
            "Name": f"UsaMember{i}",
            "TierCode": rng.choice(_TIER_CODES),
            "EnrollmentDate": f"{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}{rng.randint(2015, 2023)}",
            "FlightDate": f"{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}{rng.randint(2023, 2024)}",
        })
    return rows


def build_redemption_payloads(run_date: date, bulk_count: int = 0) -> list[dict]:
    """One JSON document per member per day (docs/01 §2). Three golden
    payloads, each demonstrating a different join outcome per docs/01 §7:
      - member_id "4"  -> RESOLVED  (only IND has this ID)
      - member_id "1"  -> AMBIGUOUS (AUS, IND, and USA all have this ID)
      - member_id "99" -> ORPHAN    (no source has this ID)
    Bulk payloads reference a random bulk member from one of the three
    disjoint bulk ID ranges, so every one resolves (RESOLVED) by construction.
    """
    feed_date = run_date.strftime("%Y%m%d")
    payloads = [
        {
            "member_id": "4",
            "feed_date": feed_date,
            "redemptions": [
                {"txn_id": "RX10091", "txn_date": feed_date, "partner": "AeroLink",
                 "miles_redeemed": 12000, "status": "COMPLETED"},
            ],
        },
        {
            "member_id": "1",
            "feed_date": feed_date,
            "redemptions": [
                {"txn_id": "RX10092", "txn_date": feed_date, "partner": "SkyPoints",
                 "miles_redeemed": 5000, "status": "PENDING"},
            ],
        },
        {
            "member_id": "99",
            "feed_date": feed_date,
            "redemptions": [
                {"txn_id": "RX10093", "txn_date": feed_date, "partner": "AeroLink",
                 "miles_redeemed": 3000, "status": "COMPLETED"},
            ],
        },
    ]
    rng = _rng(run_date, "redemption")
    bulk_offsets = [AUS_BULK_ID_OFFSET, IND_BULK_ID_OFFSET, USA_BULK_ID_OFFSET]
    for i in range(bulk_count):
        base = rng.choice(bulk_offsets)
        member_id = str(base + rng.randint(0, bulk_count - 1))
        payloads.append({
            "member_id": member_id,
            "feed_date": feed_date,
            "redemptions": [
                {
                    "txn_id": f"RXBULK{i}",
                    "txn_date": feed_date,
                    "partner": rng.choice(_PARTNERS),
                    "miles_redeemed": rng.randint(1000, 20000),
                    "status": rng.choice(_STATUSES),
                },
            ],
        })
    return payloads


def _write_xlsx(rows: list[dict], columns: list[str], path: Path) -> None:
    # write_only mode streams rows directly rather than holding Cell objects
    # for the whole sheet in memory - the difference is negligible at a few
    # rows but significant at hundreds of thousands (docs/03 §6).
    wb = Workbook(write_only=True)
    ws = wb.create_sheet()
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


def generate(run_date: date, out_dir: Path, bulk_count: int = 0) -> dict[str, Path]:
    """Writes all four daily fixture files and returns their paths, keyed by
    source name (aus, ind, usa, redemption). bulk_count is passed identically
    to all four builders, so bulk member IDs and bulk redemption references
    stay consistent with each other."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = run_date.strftime("%Y%m%d")

    paths = {
        "aus": out_dir / f"aus_member_{stamp}.xlsx",
        "ind": out_dir / f"ind_member_{stamp}.csv",
        "usa": out_dir / f"usa_member_{stamp}.csv",
        "redemption": out_dir / f"redemption_{stamp}.json",
    }

    _write_xlsx(build_aus_rows(run_date, bulk_count), AUS_COLUMNS, paths["aus"])
    _write_csv(build_ind_rows(run_date, bulk_count), IND_COLUMNS, paths["ind"])
    _write_csv(build_usa_rows(run_date, bulk_count), USA_COLUMNS, paths["usa"])
    _write_ndjson(build_redemption_payloads(run_date, bulk_count), paths["redemption"])

    return paths


def _parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--out-dir", default="landing", help="output directory (default: landing/)")
    parser.add_argument(
        "--record-count", type=int, default=DEFAULT_BULK_RECORD_COUNT,
        help=f"bulk records per source, in addition to the fixed edge-case rows "
             f"(default: {DEFAULT_BULK_RECORD_COUNT})",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    run_date = date.fromisoformat(args.run_date)
    paths = generate(run_date, Path(args.out_dir), bulk_count=args.record_count)
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
