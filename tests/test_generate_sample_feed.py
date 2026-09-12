"""
Tests for demo/generate_sample_feed.py — written before the implementation exists
(docs/04_Engineering_Practices.md §1, step 1: Red).

Defines the contract for the fixture generator described in
docs/03_Technical_Build_Plan.md §3, against the real per-country source shapes
catalogued in docs/01_Design_Specification.md §2 and docs/05_Source_Data_Analysis.md.

Expected public API (demo/generate_sample_feed.py):
    build_aus_rows(run_date: date) -> list[dict]
    build_ind_rows(run_date: date) -> list[dict]
    build_usa_rows(run_date: date) -> list[dict]
    build_redemption_payloads(run_date: date) -> list[dict]
    generate(run_date: date, out_dir: Path) -> dict[str, Path]
"""
from datetime import date

# Deliberately a plain import, not pytest.importorskip: until demo/generate_sample_feed.py
# exists, this must fail collection loudly (red), not skip quietly.
import generate_sample_feed

RUN_DATE_1 = date(2024, 1, 15)
RUN_DATE_2 = date(2024, 1, 16)


def _is_ambiguous_usa_date(value: str) -> bool:
    """A concatenated MDYYYY/MMDDYYYY string is ambiguous if more than one
    (month, day) split of it is calendar-valid. Mirrors the defect catalogued
    in docs/01_Design_Specification.md §4 (e.g. '1052022' -> Jan 5 or Oct 5)."""
    digits = value
    valid_splits = 0
    for month_len in (1, 2):
        day_len = len(digits) - 4 - month_len
        if day_len not in (1, 2):
            continue
        month_str, day_str, year_str = (
            digits[:month_len],
            digits[month_len : month_len + day_len],
            digits[month_len + day_len :],
        )
        try:
            date(int(year_str), int(month_str), int(day_str))
            valid_splits += 1
        except ValueError:
            continue
    return valid_splits > 1


class TestAusRows:
    def test_contains_literal_null_dob(self):
        rows = generate_sample_feed.build_aus_rows(RUN_DATE_1)
        assert any(r["Date of Birth"] == "NULL" for r in rows), (
            "expected at least one AUS row with the literal string 'NULL' as DOB, "
            "per docs/01 §2 / docs/05 §1"
        )

    def test_contains_invalid_enrollment_date_string(self):
        rows = generate_sample_feed.build_aus_rows(RUN_DATE_1)

        def _is_invalid_date_string(v) -> bool:
            if not isinstance(v, str):
                return False
            try:
                y, m, d = v.split("-")
                date(int(y), int(m), int(d))
                return False
            except (ValueError, IndexError):
                return True

        assert any(_is_invalid_date_string(r["Date of Enrollment"]) for r in rows), (
            "expected at least one AUS row with an invalid date string (e.g. '2021-13-13'), "
            "per docs/01 §2 / docs/05 §1"
        )

    def test_has_expected_columns(self):
        rows = generate_sample_feed.build_aus_rows(RUN_DATE_1)
        expected = {
            "Unique ID", "Member Name", "Tier Type",
            "Date of Birth", "Date of Enrollment", "Date of Flight",
        }
        assert expected.issubset(rows[0].keys())


class TestIndRows:
    def test_dates_are_m_d_yyyy_text(self):
        rows = generate_sample_feed.build_ind_rows(RUN_DATE_1)
        import re
        pattern = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
        for r in rows:
            assert pattern.match(r["EnrollmentDate"]), r["EnrollmentDate"]
            assert pattern.match(r["Flight Date"]), r["Flight Date"]

    def test_contains_both_individual_and_corporate(self):
        rows = generate_sample_feed.build_ind_rows(RUN_DATE_1)
        values = {r["Individual or Corporate"] for r in rows}
        assert values == {"I", "C"}, (
            "expected both membership_type values exercised, per docs/01 §2"
        )


class TestUsaRows:
    def test_has_no_dob_column(self):
        rows = generate_sample_feed.build_usa_rows(RUN_DATE_1)
        assert "DOB" not in rows[0].keys(), (
            "USA.csv carries no DOB column at all — see docs/01 §2"
        )

    def test_contains_an_ambiguous_date(self):
        rows = generate_sample_feed.build_usa_rows(RUN_DATE_1)
        dates = [r["EnrollmentDate"] for r in rows] + [r["FlightDate"] for r in rows]
        assert any(_is_ambiguous_usa_date(d) for d in dates), (
            "expected at least one genuinely ambiguous concatenated date "
            "(two valid month/day splits), per docs/01 §4"
        )


class TestRedemptionPayloads:
    def test_member_ids_reference_generated_members(self):
        ind_rows = generate_sample_feed.build_ind_rows(RUN_DATE_1)
        payloads = generate_sample_feed.build_redemption_payloads(RUN_DATE_1)
        ind_ids = {str(r["ID"]) for r in ind_rows}
        assert any(p["member_id"] in ind_ids for p in payloads), (
            "at least one redemption should reference a member that actually "
            "exists in the day's generated member rows"
        )


class TestGenerate:
    def test_writes_all_four_files(self, tmp_path):
        paths = generate_sample_feed.generate(RUN_DATE_1, tmp_path)
        assert set(paths.keys()) == {"aus", "ind", "usa", "redemption"}
        assert paths["aus"].suffix == ".xlsx" and paths["aus"].exists()
        assert paths["ind"].suffix == ".csv" and paths["ind"].exists()
        assert paths["usa"].suffix == ".csv" and paths["usa"].exists()
        assert paths["redemption"].suffix == ".json" and paths["redemption"].exists()

    def test_second_run_date_changes_a_tracked_attribute(self, tmp_path):
        """Replaces the earlier (incorrect) 'member changes country' scenario —
        see docs/01 §7.3/§9 and docs/03 §5 Phase 5: a country change mints an
        uncorrelated member_key by construction, so it cannot be represented as
        the same member changing on a later run date. What IS in scope, and
        what this fixture must demonstrate, is a tracked non-country attribute
        (e.g. tier_code) changing for the *same* member_key across two dates."""
        day1_dir = tmp_path / "day1"
        day2_dir = tmp_path / "day2"
        paths_1 = generate_sample_feed.generate(RUN_DATE_1, day1_dir)
        paths_2 = generate_sample_feed.generate(RUN_DATE_2, day2_dir)

        rows_1 = generate_sample_feed.build_ind_rows(RUN_DATE_1)
        rows_2 = generate_sample_feed.build_ind_rows(RUN_DATE_2)
        by_id_1 = {r["ID"]: r for r in rows_1}
        by_id_2 = {r["ID"]: r for r in rows_2}

        changed = [
            member_id
            for member_id in by_id_1
            if member_id in by_id_2
            and by_id_1[member_id]["TierCode"] != by_id_2[member_id]["TierCode"]
        ]
        assert changed, (
            "expected at least one member_key (same source ID, same country) "
            "whose TierCode differs between the two run dates"
        )
