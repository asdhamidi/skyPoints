# SkyPoints — Data Design Specification

Defines the canonical data model, source-to-canonical mapping, transformation rules, and validation rules for the SkyPoints member-profile and redemption pipeline. This is the data contract the dbt project (`03_Technical_Build_Plan.md`) is built against.

---

## 1. Canonical Member Profile Schema

| Column | Type | Mandatory | Origin | Notes |
|---|---|---|---|---|
| `member_key` | VARCHAR | Y | derived | `country_code \|\| '-' \|\| member_id` — synthesized surrogate key, see §4 |
| `member_id` | VARCHAR(18) | Y | source | source-local identifier, not globally unique across sources |
| `member_name` | VARCHAR(255) | Y | source | |
| `dob` | DATE | N | source | NULL where source does not supply it |
| `enrollment_date` | DATE | Y | source | |
| `last_flight_date` | DATE | N | source | |
| `tier_code` | VARCHAR(5) | N | source | |
| `agent_name` | VARCHAR(255) | N | source | NULL for all sources currently onboarded |
| `state` | VARCHAR(5) | N | source | NULL for all sources currently onboarded |
| `country_code` | VARCHAR(3) | Y | derived | assigned from source identity, never parsed from a data column — see §3 |
| `post_code` | VARCHAR(10) | N | source | stored as VARCHAR, not INT — see §9 |
| `is_active` | CHAR(1) | N | source | NULL for all sources currently onboarded |
| `membership_type` | VARCHAR(20) | N | source | populated only where the source provides it (`IND`) |
| `age` | NUMBER | N | derived | see §7.1 |
| `stale_member_flag` | BOOLEAN | N | derived | see §7.2 |
| `source_system` | VARCHAR | Y | derived | `AUS` \| `IND` \| `USA` |
| `feed_date` | DATE | Y | derived | business date the extract represents |
| `load_ts` | TIMESTAMP_NTZ | Y | derived | pipeline load timestamp |

---

## 2. Source Systems

| Source | Format | Columns supplied | Country derivation | Defects present in the data |
|---|---|---|---|---|
| `AUS.xlsx` | Excel workbook | `Unique ID, Member Name, Tier Type, Date of Birth, Date of Enrollment, Date of Flight` | fixed `AUS` (file identity) | DOB cell containing literal string `"NULL"`; enrollment-date cell containing invalid string `"2021-13-13"` (month 13) |
| `IND.csv` | CSV, comma-delimited | `ID, Name, DOB, TierCode, EnrollmentDate, Individual or Corporate, Flight Date` | fixed `IND` (file identity) | dates in `M/D/YYYY` text form; carries `Individual or Corporate`, mapped to `membership_type` |
| `USA.csv` | CSV, comma-delimited | `ID, Name, TierCode, EnrollmentDate, FlightDate` | fixed `USA` (file identity) | no `DOB` column at all; dates are digit-concatenated with no delimiter, two of six sample values are provably ambiguous (see §5) |
| Redemption feed | JSON, one document per member per day | `member_id, feed_date, redemptions[]` | not applicable — joined to member profile post-harmonization | none observed |

None of the three per-country sources carry `Country`, `State`, `Agent_Name`, `Post_Code`, or `Is_Active` as data columns. `Country` is assigned at ingestion time from which source file a row came from, not read from any field.

The header/detail pipe-delimited layout referenced in the assessment brief is treated as the definition of the **canonical schema** (§1), not as a fourth literal data source — no per-country source currently delivers data in that shape.

---

## 3. Identifier Strategy

`member_id` is source-local: all three sources independently number members `1, 2, 3, …`, so identical values collide across sources with no meaning in common.

`member_key = country_code || '-' || member_id` is synthesized at harmonization time and used as the uniqueness key throughout staging, marts, and validation.

**Limitation:** this key changes if a member is re-issued under a different `country_code`/`member_id` pair (a genuine cross-country move, arriving as a new local ID in a different source file). Detecting that requires identity resolution (e.g. name + DOB matching) against a source of truth not present in the data supplied. Country-move tracking in this design (§7.3) is therefore scoped to: *a `member_key` that reappears with a different `country_code` value under the same key* — a real member re-issued a new source-local ID under a different country is out of scope.

---

## 4. Date Handling

Every date is parsed with an explicit, source-specific format mask. No format auto-detection is used anywhere in the pipeline.

| Source | Field(s) | Format | Failure handling |
|---|---|---|---|
| `AUS.xlsx` | all dates | native Excel datetime, except cells stored as text | `TRY_TO_DATE`; a non-parseable value (`"NULL"`, `"2021-13-13"`) resolves to `NULL` with a logged reason, not a load failure |
| `IND.csv` | all dates | `M/D/YYYY` | `TO_DATE(value, 'MM/DD/YYYY')` |
| `USA.csv` | all dates | digits concatenated, no delimiter, variable width | parsed only when digit count and calendar validity force one unique split; any value with more than one valid interpretation (e.g. `1052022` → Jan 5 or Oct 5) is written to a quarantine table, never guessed |

---

## 5. Layered Data Model

**RAW** — one table per source, string-typed (no casting on load), carries `source_file_name` and `load_ts`:
`RAW.AUS_MEMBER_PROFILE`, `RAW.IND_MEMBER_PROFILE`, `RAW.USA_MEMBER_PROFILE`, `RAW.REDEMPTION_FEED`.
DDL: `setup/raw_tables.sql`.

`AUS.xlsx` is converted to CSV ahead of staging — Snowflake `COPY INTO` has no native Excel file format, so an Excel→CSV conversion step is a required pipeline component (see `03_Technical_Build_Plan.md` §3).

**STAGING** — one harmonization model per source, mapping source columns to the canonical schema and computing `member_key`/`country_code`/derived columns, unioned into a single canonical model:
`stg_member_profile_aus`, `stg_member_profile_ind`, `stg_member_profile_usa` → `stg_member_profile` (UNION ALL, still pre-validation) → `stg_member_profile_valid` (mandatory-field gate; everything downstream is built on this, not `stg_member_profile`) with `rejected_member_records` as its DLQ counterpart (§10). Redemptions: `stg_redemptions` (flattened).

**MARTS** — one physical table per country, plus one global redemptions table:
`MARTS.TABLE_AUS`, `MARTS.TABLE_IND`, `MARTS.TABLE_USA`, …, `MARTS.REDEMPTIONS`.

---

## 6. Transformation Rules

**6.1 Age** — `DATEDIFF(year, dob, feed_date)`, adjusted down by one where the birthday has not yet occurred in `feed_date`'s year; `NULL` where `dob` is `NULL` (every `USA` row).

**6.2 Stale_Member_Flag** — `DATEDIFF(day, last_flight_date, feed_date) > 90`; `NULL` where `last_flight_date` is `NULL`.

**6.3 Attribute history tracking** — a dbt snapshot over `stg_member_profile`, keyed on `member_key`, strategy `check` on the non-key attributes (`tier_code`, `last_flight_date`, `is_active`, …). Produces `dbt_valid_from`/`dbt_valid_to` per attribute version automatically. `country_code` is part of `member_key` itself (§3), so it is never a tracked attribute here — a country change cannot appear as a new version of an existing `member_key`; it can only appear as an entirely new, uncorrelated `member_key`, per the limitation in §3.

**6.4 Current-attribute resolution** — `int_member_profile_final` selects the snapshot row per `member_key` where `dbt_valid_to IS NULL`: the single source of truth for a member's current tier/flight-date/status. Which physical country table a `member_key` belongs to is fixed at the point the key is created (§3), not something the snapshot resolves.

**6.5 Country table generation** — one `CREATE OR REPLACE TABLE MARTS.TABLE_<COUNTRY> AS SELECT * FROM int_member_profile_final WHERE country_code = '<code>'` per row of `seeds/country_reference.csv`, issued by a single macro loop. Adding a country is a seed-file edit, not a new model.

---

## 7. Redemption Feed

Raw JSON lands as one row per source document, `payload` as `VARIANT`. `stg_redemptions` flattens `payload:redemptions` via `LATERAL FLATTEN` into one row per transaction: `member_id, feed_date, txn_id, txn_date, partner, miles_redeemed, status`.

**Join resolution to member profile.** The feed's `member_id` is a bare identifier with no country attached — and because `AUS`/`IND`/`USA` all use overlapping small local ID ranges (§2 — all three files number members `1, 2, 3…`), a bare `member_id` routinely matches more than one country at once (e.g. `"1"` is simultaneously AUS's Mike, IND's Vikas, and USA's Sam). This is the same missing-global-identity gap already noted in §3/§9, surfacing again here — not a new limitation. The sample redemption payload in the assessment brief (`"member_id": "223457"`) is itself only consistent with the brief's illustrative unified flat file's ID space, not with the real per-country files' local IDs, which is further evidence no single shared ID space is actually available.

`marts.redemptions` therefore joins `stg_redemptions` to `int_member_profile_final` on `member_id` and classifies every redemption by match count rather than assuming a clean join:
- **exactly one** `country_code` matches → resolved, `country_code` attached
- **zero** matches → orphan — logged, not silently dropped
- **more than one** matches → ambiguous — logged, **never arbitrarily resolved to one country**

`marts.redemptions` is kept as a single global table (not split per country), consistent with the "resolved/orphan/ambiguous" classification not being a per-country concept.

---

## 8. Validation Rules

| Rule | Applies to | Failure action |
|---|---|---|
| `not_null` | `member_name`, `member_id`, `enrollment_date` | excluded from `stg_member_profile_valid`, routed to the DLQ (§10) |
| `unique` | `member_key` (not `member_name`) | reject duplicate, log |
| `country_code` must exist in `country_reference` seed | all member rows | reject row, log |
| ambiguous date | `USA` rows only (§4) | resolves to `NULL`; if the affected field is `enrollment_date` (mandatory), the row is routed to the DLQ (§10) same as any other mandatory-field failure — never guessed |
| `txn_id` unique | redemptions | reject duplicate, log |
| `member_id` referential integrity | redemptions → member profile | classify as resolved (exactly one country matches) / orphan (none match) / ambiguous (more than one matches) — log orphan and ambiguous, never guess a country for an ambiguous match (§7) |
| raw field count matches source's expected column count | all raw ingestion | `ERROR_ON_COLUMN_COUNT_MISMATCH = TRUE` on `CSV_FORMAT` rejects the load outright (`setup/snowflake_bootstrap.sql`); `assert_raw_field_count_matches_spec` is the defense-in-depth check for anything that loads with the right count but blank/malformed content |
| `post_code` type | all sources | stored as VARCHAR; INT is never used |

---

## 9. Assumptions and Limitations

- Cross-country member-move detection is limited to a `member_key` reappearing under a different `country_code`; a true physical move that arrives as a new local ID in a new source file is not detected by this design (§3).
- The redemption feed's `member_id` cannot be reliably attributed to one country from the data given: `AUS`/`IND`/`USA`'s overlapping local ID ranges mean a bare `member_id` frequently matches more than one country's member at once (§7). A resolved match is not a guarantee of correctness, only an absence of ambiguity in this data; a genuinely reliable join needs the same global identity system missing per §3.
- The flat-file DOB format referenced in the assessment brief (`MMDDYYYY` vs. `DDMMYYYY`) is assumed `MMDDYYYY`, unconfirmed.
- The country set is assumed fixed to `seeds/country_reference.csv`; a new country requires a seed update, not a code change.
- Each per-country source is assumed to deliver a full daily snapshot of its members, not a delta; if any source instead delivers only changed rows, the staging de-duplication logic in §6.4 must be revised to merge against prior state rather than replace it.

---

## 10. Dead Letter Queue

A member row failing a mandatory-field check (`member_name`, `member_id`, or `enrollment_date` null — including an `enrollment_date` that failed to parse, e.g. AUS's invalid `"2021-13-13"`) is excluded from the pipeline's main flow rather than propagating a silent `NULL` into a column the rest of the design treats as guaranteed non-null.

**Split:**
- `stg_member_profile` — the union of the three per-source models, pre-validation; still contains rejected rows and carries `dob_raw`/`enrollment_date_raw`/`last_flight_date_raw` passthrough columns (the original unparsed string, for explaining a rejection). Nothing downstream reads this model directly.
- `stg_member_profile_valid` — `stg_member_profile` filtered to rows with all three mandatory fields present, canonical columns only (no `*_raw`). The snapshot, and everything built on it, reads this model.
- `rejected_member_records` — the DLQ. Same source rows, inverse filter, plus a `rejection_reason` column (`MISSING_MEMBER_NAME`, `MISSING_MEMBER_ID`, or `INVALID_ENROLLMENT_DATE: raw value was '<value>'`). Materialized incremental and append-only: a source resending the same bad row on a later day rejects again as its own dated record, rather than being collapsed into one — so whether a defect is still happening or was fixed stays visible.

**Guarantee:** `count(stg_member_profile) = count(stg_member_profile_valid) + count(rejected_member_records)` for any given `feed_date`, checked by `assert_no_member_rows_lost_to_dlq_split`.

**Scope:** only the three mandatory fields trigger a DLQ entry. An optional field (`dob`, `last_flight_date`) failing to parse — including a genuinely ambiguous USA date — still resolves to `NULL` and the row still flows through normally; that was always the correct behavior for an optional field and remains unchanged. The DLQ only exists for the case where a `NULL` would otherwise silently violate a mandatory-field guarantee the rest of the design depends on.

**Observability:** `publish_run_summary` (`airflow/scripts/snowflake_tasks.py`) logs a count per `rejection_reason` category for the latest `feed_date` alongside the existing per-country row counts and redemption match-status counts.
