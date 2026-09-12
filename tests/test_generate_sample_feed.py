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
import csv
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


def _country_member_ids(run_date):
    """member_id sets per country, as strings, for checking how many countries
    a given redemption member_id matches — mirrors the join classification in
    docs/01_Design_Specification.md §7 (resolved / orphan / ambiguous)."""
    aus_ids = {str(r["Unique ID"]) for r in generate_sample_feed.build_aus_rows(run_date)}
    ind_ids = {str(r["ID"]) for r in generate_sample_feed.build_ind_rows(run_date)}
    usa_ids = {str(r["ID"]) for r in generate_sample_feed.build_usa_rows(run_date)}
    return aus_ids, ind_ids, usa_ids


def _matching_country_count(member_id, id_sets):
    return sum(member_id in ids for ids in id_sets)


class TestRedemptionPayloads:
    def test_member_ids_reference_generated_members(self):
        ind_rows = generate_sample_feed.build_ind_rows(RUN_DATE_1)
        payloads = generate_sample_feed.build_redemption_payloads(RUN_DATE_1)
        ind_ids = {str(r["ID"]) for r in ind_rows}
        assert any(p["member_id"] in ind_ids for p in payloads), (
            "at least one redemption should reference a member that actually "
            "exists in the day's generated member rows"
        )

    def test_includes_a_resolved_match(self):
        """Exactly one country's rows contain this member_id — docs/01 §7 'resolved'."""
        id_sets = _country_member_ids(RUN_DATE_1)
        payloads = generate_sample_feed.build_redemption_payloads(RUN_DATE_1)
        assert any(_matching_country_count(p["member_id"], id_sets) == 1 for p in payloads), (
            "expected at least one redemption whose member_id resolves to exactly "
            "one country, per docs/01 §7"
        )

    def test_includes_an_orphan_match(self):
        """No country's rows contain this member_id — docs/01 §7/§8 'orphan'."""
        id_sets = _country_member_ids(RUN_DATE_1)
        payloads = generate_sample_feed.build_redemption_payloads(RUN_DATE_1)
        assert any(_matching_country_count(p["member_id"], id_sets) == 0 for p in payloads), (
            "expected at least one redemption whose member_id matches no country at "
            "all, per docs/01 §7/§8"
        )

    def test_includes_an_ambiguous_match(self):
        """More than one country's rows contain this member_id — docs/01 §7 'ambiguous',
        the common case given AUS/IND/USA's overlapping local ID ranges."""
        id_sets = _country_member_ids(RUN_DATE_1)
        payloads = generate_sample_feed.build_redemption_payloads(RUN_DATE_1)
        assert any(_matching_country_count(p["member_id"], id_sets) > 1 for p in payloads), (
            "expected at least one redemption whose member_id matches more than one "
            "country at once, per docs/01 §7"
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


class TestBulkGeneration:
    """bulk_count adds realistic, deterministic volume on top of the golden
    edge-case rows above — it never replaces or reorders them, so every
    existing golden-row assertion in this file keeps passing unchanged with
    the default bulk_count=0. See docs/03 for why 250,000/source is the CLI
    default (production-scale demo volume) while tests use small counts."""

    def test_bulk_count_appends_without_disturbing_golden_rows(self):
        golden = generate_sample_feed.build_aus_rows(RUN_DATE_1)
        with_bulk = generate_sample_feed.build_aus_rows(RUN_DATE_1, bulk_count=5)
        assert with_bulk[: len(golden)] == golden
        assert len(with_bulk) == len(golden) + 5

    def test_bulk_ids_are_disjoint_across_sources(self):
        """AUS/IND/USA bulk IDs live in separate numeric ranges specifically so
        a bulk redemption can resolve to exactly one country by construction —
        unlike the golden 1-4 range, which deliberately collides across all
        three sources to reproduce the real files (docs/01 §3, §7)."""
        aus_ids = {r["Unique ID"] for r in generate_sample_feed.build_aus_rows(RUN_DATE_1, bulk_count=10)[3:]}
        ind_ids = {r["ID"] for r in generate_sample_feed.build_ind_rows(RUN_DATE_1, bulk_count=10)[4:]}
        usa_ids = {r["ID"] for r in generate_sample_feed.build_usa_rows(RUN_DATE_1, bulk_count=10)[3:]}
        assert not (aus_ids & ind_ids)
        assert not (aus_ids & usa_ids)
        assert not (ind_ids & usa_ids)

    def test_bulk_usa_dates_are_never_ambiguous(self):
        """Bulk data is meant to exercise volume, not the ambiguity-quarantine
        path — that's what the golden John row already covers on its own."""
        rows = generate_sample_feed.build_usa_rows(RUN_DATE_1, bulk_count=50)
        bulk_rows = rows[3:]
        dates = [r["EnrollmentDate"] for r in bulk_rows] + [r["FlightDate"] for r in bulk_rows]
        assert not any(_is_ambiguous_usa_date(d) for d in dates)

    def test_bulk_generation_is_deterministic(self):
        rows_a = generate_sample_feed.build_ind_rows(RUN_DATE_1, bulk_count=20)
        rows_b = generate_sample_feed.build_ind_rows(RUN_DATE_1, bulk_count=20)
        assert rows_a == rows_b

    def test_bulk_redemptions_resolve_to_exactly_one_country(self):
        bulk_count = 20
        aus_ids = {str(r["Unique ID"]) for r in generate_sample_feed.build_aus_rows(RUN_DATE_1, bulk_count)}
        ind_ids = {str(r["ID"]) for r in generate_sample_feed.build_ind_rows(RUN_DATE_1, bulk_count)}
        usa_ids = {str(r["ID"]) for r in generate_sample_feed.build_usa_rows(RUN_DATE_1, bulk_count)}
        payloads = generate_sample_feed.build_redemption_payloads(RUN_DATE_1, bulk_count)
        bulk_payloads = payloads[3:]  # the first 3 are the golden resolved/ambiguous/orphan cases
        assert len(bulk_payloads) == bulk_count
        for p in bulk_payloads:
            match_count = sum(p["member_id"] in ids for ids in (aus_ids, ind_ids, usa_ids))
            assert match_count == 1, f"member_id {p['member_id']} should resolve to exactly one country"

    def test_default_bulk_record_count_is_250000(self):
        assert generate_sample_feed.DEFAULT_BULK_RECORD_COUNT == 250_000

    def test_generate_wires_bulk_count_through_to_every_file(self, tmp_path):
        paths = generate_sample_feed.generate(RUN_DATE_1, tmp_path, bulk_count=10)
        with open(paths["ind"], newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 4 + 10  # 4 golden IND rows + 10 bulk
