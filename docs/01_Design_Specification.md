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

`AUS.xlsx` is converted to CSV ahead of staging — Snowflake `COPY INTO` has no native Excel file format, so an Excel→CSV conversion step is a required pipeline component (see `03_Technical_Build_Plan.md` §3).

**STAGING** — one harmonization model per source, mapping source columns to the canonical schema and computing `member_key`/`country_code`/derived columns, unioned into a single canonical model:
`stg_member_profile_aus`, `stg_member_profile_ind`, `stg_member_profile_usa` → `stg_member_profile` (UNION ALL). Redemptions: `stg_redemptions` (flattened).

**MARTS** — one physical table per country, plus one global redemptions table:
`MARTS.TABLE_AUS`, `MARTS.TABLE_IND`, `MARTS.TABLE_USA`, …, `MARTS.REDEMPTIONS`.

---

## 6. Transformation Rules

**6.1 Age** — `DATEDIFF(year, dob, feed_date)`, adjusted down by one where the birthday has not yet occurred in `feed_date`'s year; `NULL` where `dob` is `NULL` (every `USA` row).

**6.2 Stale_Member_Flag** — `DATEDIFF(day, last_flight_date, feed_date) > 90`; `NULL` where `last_flight_date` is `NULL`.

**6.3 Country-move tracking** — a dbt snapshot over `stg_member_profile`, keyed on `member_key`, strategy `check` on `country_code`. Produces `dbt_valid_from`/`dbt_valid_to` per country assignment automatically.

**6.4 Current-country resolution** — `int_member_profile_final` selects the snapshot row per `member_key` where `dbt_valid_to IS NULL`: the single source of truth for "which country table this member belongs to right now."

**6.5 Country table generation** — one `CREATE OR REPLACE TABLE MARTS.TABLE_<COUNTRY> AS SELECT * FROM int_member_profile_final WHERE country_code = '<code>'` per row of `seeds/country_reference.csv`, issued by a single macro loop. Adding a country is a seed-file edit, not a new model.

---

## 7. Redemption Feed

Raw JSON lands as one row per source document, `payload` as `VARIANT`. `stg_redemptions` flattens `payload:redemptions` via `LATERAL FLATTEN` into one row per transaction: `member_id, feed_date, txn_id, txn_date, partner, miles_redeemed, status`.

`marts.redemptions` joins `stg_redemptions` to `int_member_profile_final` on `member_id` (scoped by `country_code` resolution) to attach `country_code`, and is kept as a single global table rather than split per country.

---

## 8. Validation Rules

| Rule | Applies to | Failure action |
|---|---|---|
| `not_null` | `member_name`, `member_id`, `enrollment_date` | reject row, log |
| `unique` | `member_key` (not `member_name`) | reject duplicate, log |
| `country_code` must exist in `country_reference` seed | all member rows | reject row, log |
| ambiguous date | `USA` rows only (§4) | quarantine, never guess |
| `txn_id` unique | redemptions | reject duplicate, log |
| `member_id` referential integrity | redemptions → member profile | log orphan, do not silently drop |
| raw field count matches source's expected column count | all raw ingestion | reject file / alert |
| `post_code` type | all sources | stored as VARCHAR; INT is never used |

---

## 9. Assumptions and Limitations

- Cross-country member-move detection is limited to a `member_key` reappearing under a different `country_code`; a true physical move that arrives as a new local ID in a new source file is not detected by this design (§3).
- The flat-file DOB format referenced in the assessment brief (`MMDDYYYY` vs. `DDMMYYYY`) is assumed `MMDDYYYY`, unconfirmed.
- The country set is assumed fixed to `seeds/country_reference.csv`; a new country requires a seed update, not a code change.
- Each per-country source is assumed to deliver a full daily snapshot of its members, not a delta; if any source instead delivers only changed rows, the staging de-duplication logic in §6.4 must be revised to merge against prior state rather than replace it.
